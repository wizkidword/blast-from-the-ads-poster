"""Durable staging, rollback, and recovery for local media processing.

The transaction journal is an audit and recovery aid.  The workspace lock is
still responsible for ensuring that only one mutating operation owns a project
at a time.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Sequence
from uuid import uuid4

try:
    from app_context import AppContext
except ImportError:
    from scripts.app_context import AppContext

try:
    from atomic_io import atomic_write_json, atomic_write_text, load_json, require_json_object
except ImportError:
    from scripts.atomic_io import atomic_write_json, atomic_write_text, load_json, require_json_object

try:
    from media_processing import get_media_dimensions
except ImportError:
    from scripts.media_processing import get_media_dimensions

try:
    from media_processing import (
        INSTAGRAM_VIDEO_HEIGHT,
        INSTAGRAM_VIDEO_WIDTH,
        convert_image_to_instagram,
        convert_video_to_vertical,
        create_carousel_video_from_images,
    )
except ImportError:
    from scripts.media_processing import (
        INSTAGRAM_VIDEO_HEIGHT,
        INSTAGRAM_VIDEO_WIDTH,
        convert_image_to_instagram,
        convert_video_to_vertical,
        create_carousel_video_from_images,
    )

try:
    from media_artifacts import cleanup_temp_files, extract_video_frames
except ImportError:
    from scripts.media_artifacts import cleanup_temp_files, extract_video_frames

try:
    from manifest_service import build_post_id, write_post_manifest
except ImportError:
    from scripts.manifest_service import build_post_id, write_post_manifest

try:
    from publishing import PublishStatus
except ImportError:
    from scripts.publishing import PublishStatus

try:
    from media_rules import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
except ImportError:
    from scripts.media_rules import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

try:
    from safe_paths import normalize_relative_to, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import normalize_relative_to, require_plain_filename, resolve_existing_under, resolve_output_under

try:
    from workspace_lock import InboxClaim, OperationCancelled
except ImportError:
    from scripts.workspace_lock import InboxClaim, OperationCancelled


TRANSACTION_SCHEMA_VERSION = 1


class TransactionError(RuntimeError):
    """Raised for an invalid or failed processing transaction."""


class TransactionState(str, Enum):
    CREATED = "created"
    CLAIMED = "claimed"
    PROCESSING = "processing"
    VALIDATED = "validated"
    COMMITTED = "committed"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class TransactionResult:
    transaction_id: str
    state: TransactionState
    final_workspace: Path | None
    warnings: tuple[str, ...] = ()

    @property
    def fully_completed(self) -> bool:
        return self.state is TransactionState.ARCHIVED and not self.warnings


@dataclass(frozen=True)
class RecoveryResult:
    journal_path: Path
    action: str
    state: TransactionState
    message: str


FailureInjector = Callable[[str], None]


class ProcessingTransaction:
    """One video or one carousel group staged before any final output is touched."""

    def __init__(
        self,
        context: AppContext,
        run_id: str,
        claims: Sequence[InboxClaim],
        post_type: str,
        *,
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if not claims:
            raise TransactionError("A processing transaction requires at least one claimed source")
        self.context = context
        self.run_id = require_plain_filename(run_id)
        self.transaction_id = uuid4().hex
        self.post_type = post_type
        self.claims = tuple(claims)
        self.source_hashes = {
            claim.original_path.name: _sha256(claim.claimed_path)
            for claim in self.claims
            if claim.claimed_path.exists()
        }
        self.failure_injector = failure_injector
        self.state = TransactionState.CREATED
        self.warnings: list[str] = []
        self.created_at = _utc_now_iso()
        self.journal_dir = context.project_dir / ".transactions" / self.run_id
        self.journal_path = self.journal_dir / f"{self.transaction_id}.json"
        self.staging_root = context.outputs_dir / ".staging" / self.run_id / self.transaction_id
        self.sources_dir = self.staging_root / "sources"
        self.processed_dir = self.staging_root / "processed"
        self.workspace_dir = self.staging_root / "workspace"
        self.legacy_caption_stage = self.staging_root / "legacy-caption.txt"
        self.post_id: str | None = None
        self.final_workspace: Path | None = None
        self.external_artifacts: list[dict[str, str]] = []
        self._write_journal()

    def start(self, post_id: str) -> tuple[Path, list[Path]]:
        """Create isolated stage folders and byte-for-byte working source copies."""

        self.post_id = self._reserve_post_id(post_id)
        self.final_workspace = resolve_output_under(self.context.outputs_dir, self.post_id)
        self.staging_root.mkdir(parents=True, exist_ok=False)
        (self.workspace_dir / "media").mkdir(parents=True)
        (self.workspace_dir / "tiktok" / "media").mkdir(parents=True)
        self.sources_dir.mkdir()
        self.processed_dir.mkdir()
        self._transition(TransactionState.CLAIMED)
        self._checkpoint("after_claim")

        self._transition(TransactionState.PROCESSING)
        working_sources: list[Path] = []
        for claim in self.claims:
            claimed_path = resolve_existing_under(self.context.inbox_dir, claim.claimed_path)
            working_path = resolve_output_under(self.sources_dir, require_plain_filename(claim.original_path.name))
            shutil.copy2(claimed_path, working_path)
            if _sha256(claimed_path) != _sha256(working_path):
                raise TransactionError(f"Staged source copy did not match original bytes: {claim.original_path.name}")
            working_sources.append(working_path)
        self._write_journal()
        return self.workspace_dir, working_sources

    def staged_processed_path(self, name: str) -> Path:
        return resolve_output_under(self.processed_dir, require_plain_filename(name))

    def staged_workspace_path(self, relative_path: Path | str) -> Path:
        return resolve_output_under(self.workspace_dir, relative_path)

    def write_caption(self, caption_text: str, legacy_filename: str) -> tuple[Path, Path]:
        caption_path = self.staged_workspace_path("caption.txt")
        atomic_write_text(caption_path, caption_text)
        atomic_write_text(self.legacy_caption_stage, caption_text)
        self.external_artifacts.append(
            {
                "stage_relative_path": self._stage_relative(self.legacy_caption_stage),
                "destination_role": "captions",
                "destination_name": require_plain_filename(legacy_filename),
            }
        )
        self._write_journal()
        self._checkpoint("after_caption_generation")
        return caption_path, self.legacy_caption_stage

    def register_processed_artifact(self, staged_path: Path, destination_name: str) -> None:
        staged_path = resolve_existing_under(self.staging_root, staged_path)
        self.external_artifacts.append(
            {
                "stage_relative_path": self._stage_relative(staged_path),
                "destination_role": "processed",
                "destination_name": require_plain_filename(destination_name),
            }
        )
        self._write_journal()

    def rewrite_manifest_for_final_paths(self, manifest_path: Path, legacy_caption_path: Path) -> None:
        """Store final paths while the manifest itself is still safely staged."""

        if not self.post_id or not self.final_workspace:
            raise TransactionError("Transaction workspace has not been initialized")
        manifest_path = resolve_existing_under(self.workspace_dir, manifest_path)
        manifest = require_json_object(load_json(manifest_path, document_name="Staged post manifest"), document_name="Staged post manifest")
        final_workspace_relative = normalize_relative_to(self.context.project_dir, self.final_workspace)
        paths = manifest.setdefault("paths", {})
        if not isinstance(paths, dict):
            raise TransactionError("Staged post manifest paths must be an object")
        paths["output_dir"] = final_workspace_relative
        paths["manifest_path"] = f"{final_workspace_relative}/post_manifest.json"
        paths["caption_path"] = f"{final_workspace_relative}/caption.txt"
        paths["legacy_caption_path"] = _relative_or_absolute(self.context.project_dir, legacy_caption_path)

        for item in manifest.get("media_files", []):
            if not isinstance(item, dict) or not item.get("filename"):
                continue
            filename = require_plain_filename(str(item["filename"]))
            role = str(item.get("role") or "")
            subdir = "tiktok/media" if role == "carousel_video" else "media"
            item["relative_path"] = f"{final_workspace_relative}/{subdir}/{filename}"
        atomic_write_json(manifest_path, manifest)
        self._write_journal()
        self._checkpoint("after_manifest_generation")

    def validate(self, expected_media_count: int) -> None:
        if self.state is not TransactionState.PROCESSING:
            raise TransactionError(f"Cannot validate transaction from state {self.state.value}")
        if expected_media_count <= 0:
            raise TransactionError("Transaction must contain at least one media artifact")
        required = [self.workspace_dir / "caption.txt", self.workspace_dir / "post_manifest.json"]
        required.extend(self._workspace_media_files())
        if len(self._workspace_media_files()) != expected_media_count:
            raise TransactionError(
                f"Expected {expected_media_count} staged media artifact(s), found {len(self._workspace_media_files())}"
            )
        for path in required:
            if not path.is_file() or path.stat().st_size <= 0:
                raise TransactionError(f"Required staged artifact is missing or empty: {path.name}")
        for path in self._workspace_media_files():
            self._validate_media(path)
        self._validate_manifest_references(self.workspace_dir / "post_manifest.json")
        self._transition(TransactionState.VALIDATED)
        self._checkpoint("after_validation")

    def commit_and_archive(self) -> TransactionResult:
        if self.state is not TransactionState.VALIDATED or not self.final_workspace:
            raise TransactionError("Only validated staging workspaces can be committed")
        self._checkpoint("before_commit")
        if self.final_workspace.exists():
            raise TransactionError(f"Final output workspace already exists: {self.final_workspace.name}")
        os.replace(self.workspace_dir, self.final_workspace)
        self._transition(TransactionState.COMMITTED)
        try:
            self._checkpoint("after_commit_before_archive")
            self._materialize_external_artifacts()
            self._archive_claims()
        except Exception as exc:
            self._warn(f"Committed workspace needs recovery before final archival: {exc}")
            return TransactionResult(self.transaction_id, self.state, self.final_workspace, tuple(self.warnings))

        self._transition(TransactionState.ARCHIVED)
        shutil.rmtree(self.staging_root, ignore_errors=True)
        return TransactionResult(self.transaction_id, self.state, self.final_workspace, tuple(self.warnings))

    def rollback(self, reason: str) -> TransactionResult:
        """Restore pre-commit claims and delete only this transaction's staging tree."""

        if self.state in {TransactionState.COMMITTED, TransactionState.ARCHIVED}:
            raise TransactionError("Committed transactions must be recovered, not rolled back")
        restore_errors: list[str] = []
        for claim in self.claims:
            if claim.claimed_path.exists() and not claim.release():
                restore_errors.append(claim.original_path.name)
            if claim.original_path.exists() and _sha256(claim.original_path) != _sha256_from_journal(self._source_record(claim)):
                restore_errors.append(f"{claim.original_path.name} (hash mismatch)")
        shutil.rmtree(self.staging_root, ignore_errors=True)
        if restore_errors:
            self._warn(f"Rollback could not restore source(s): {', '.join(restore_errors)}")
            self._write_journal()
            return TransactionResult(self.transaction_id, self.state, self.final_workspace, tuple(self.warnings))
        self._transition(TransactionState.ROLLED_BACK, reason=reason)
        return TransactionResult(self.transaction_id, self.state, self.final_workspace, tuple(self.warnings))

    def _archive_claims(self) -> None:
        archive_dir = self.context.inbox_dir / ".archive" / self.run_id
        archive_dir.mkdir(parents=True, exist_ok=True)
        for claim in self.claims:
            if not claim.claimed_path.exists():
                continue
            destination = resolve_output_under(archive_dir, require_plain_filename(claim.original_path.name))
            if destination.exists():
                raise TransactionError(f"Archive destination already exists for {claim.original_path.name}")
            expected_hash = _sha256_from_journal(self._source_record(claim))
            os.rename(claim.claimed_path, destination)
            if _sha256(destination) != expected_hash:
                raise TransactionError(f"Archived original hash mismatch: {claim.original_path.name}")
        self._write_journal()

    def _materialize_external_artifacts(self) -> None:
        for artifact in self.external_artifacts:
            staged_path = resolve_existing_under(self.staging_root, self.staging_root / artifact["stage_relative_path"])
            if artifact["destination_role"] == "processed":
                destination = resolve_output_under(self.context.processed_dir, artifact["destination_name"])
            elif artifact["destination_role"] == "captions":
                destination = resolve_output_under(self.context.captions_dir, artifact["destination_name"])
            else:
                raise TransactionError(f"Unsupported external artifact role: {artifact['destination_role']}")
            _atomic_copy(staged_path, destination)
        self._write_journal()

    def _validate_media(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            if get_media_dimensions(path) is None:
                raise TransactionError(f"Staged image is unreadable: {path.name}")
        elif suffix in VIDEO_EXTENSIONS:
            if get_media_dimensions(path) is None:
                raise TransactionError(f"Staged video could not be probed: {path.name}")
        else:
            raise TransactionError(f"Unsupported staged media artifact: {path.name}")

    def _validate_manifest_references(self, manifest_path: Path) -> None:
        manifest = require_json_object(load_json(manifest_path, document_name="Staged post manifest"), document_name="Staged post manifest")
        serialized = json.dumps(manifest, sort_keys=True)
        if ".staging" in serialized or str(self.staging_root) in serialized:
            raise TransactionError("Staged manifest still references a staging path")
        expected_prefix = normalize_relative_to(self.context.project_dir, self.final_workspace or self.workspace_dir)
        for item in manifest.get("media_files", []):
            if not isinstance(item, dict) or not str(item.get("relative_path") or "").startswith(expected_prefix + "/"):
                raise TransactionError("Staged manifest references media outside the final workspace")

    def _workspace_media_files(self) -> list[Path]:
        paths: list[Path] = []
        for root in (self.workspace_dir / "media", self.workspace_dir / "tiktok" / "media"):
            if root.exists():
                paths.extend(path for path in root.iterdir() if path.is_file())
        return sorted(paths)

    def _reserve_post_id(self, candidate: str) -> str:
        candidate = require_plain_filename(candidate)
        output = resolve_output_under(self.context.outputs_dir, candidate)
        counter = 1
        while output.exists():
            output = resolve_output_under(self.context.outputs_dir, f"{candidate}-{counter}")
            counter += 1
        return output.name

    def _source_record(self, claim: InboxClaim) -> dict[str, Any]:
        for record in self._journal_payload().get("sources", []):
            if record.get("original_name") == claim.original_path.name:
                return record
        raise TransactionError(f"Source is not present in transaction journal: {claim.original_path.name}")

    def _transition(self, state: TransactionState, *, reason: str | None = None) -> None:
        self.state = state
        self._write_journal(reason=reason)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self._write_journal()

    def _checkpoint(self, name: str) -> None:
        self._write_journal()
        if self.failure_injector is not None:
            self.failure_injector(name)

    def _stage_relative(self, path: Path) -> str:
        return normalize_relative_to(self.staging_root, path)

    def _journal_payload(self) -> dict[str, Any]:
        return {
            "schema_version": TRANSACTION_SCHEMA_VERSION,
            "transaction_id": self.transaction_id,
            "run_id": self.run_id,
            "post_type": self.post_type,
            "state": self.state.value,
            "created_at": self.created_at,
            "post_id": self.post_id,
            "paths": {
                "staging_root": normalize_relative_to(self.context.project_dir, self.staging_root),
                "workspace": normalize_relative_to(self.context.project_dir, self.workspace_dir),
                "final_workspace": normalize_relative_to(self.context.project_dir, self.final_workspace)
                if self.final_workspace
                else None,
            },
            "sources": [
                {
                    "original_name": require_plain_filename(claim.original_path.name),
                    "original_relative_path": normalize_relative_to(self.context.inbox_dir, claim.original_path),
                    "claimed_relative_path": normalize_relative_to(self.context.inbox_dir, claim.claimed_path),
                    "archive_relative_path": f".archive/{self.run_id}/{require_plain_filename(claim.original_path.name)}",
                    "sha256": self.source_hashes.get(claim.original_path.name)
                    or _sha256_if_exists(claim.claimed_path)
                    or _sha256_if_exists(claim.original_path),
                }
                for claim in self.claims
            ],
            "external_artifacts": list(self.external_artifacts),
            "warnings": list(self.warnings),
            "updated_at": _utc_now_iso(),
        }

    def _write_journal(self, *, reason: str | None = None) -> None:
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        payload = self._journal_payload()
        if reason:
            payload["reason"] = reason
        atomic_write_json(self.journal_path, payload)


def list_incomplete_transactions(context: AppContext) -> list[Path]:
    journal_root = context.project_dir / ".transactions"
    if not journal_root.exists():
        return []
    journals: list[Path] = []
    for path in sorted(journal_root.rglob("*.json")):
        try:
            payload = require_json_object(load_json(path, document_name="Transaction journal"), document_name="Transaction journal")
            state = TransactionState(str(payload.get("state")))
        except (OSError, ValueError):
            continue
        if state not in {TransactionState.ARCHIVED, TransactionState.ROLLED_BACK}:
            journals.append(path)
    return journals


def recover_incomplete_transactions(context: AppContext) -> list[RecoveryResult]:
    """Safely restore pre-commit work or finish archival for committed work."""

    results: list[RecoveryResult] = []
    for journal_path in list_incomplete_transactions(context):
        payload = require_json_object(load_json(journal_path, document_name="Transaction journal"), document_name="Transaction journal")
        state = TransactionState(str(payload["state"]))
        if state in {TransactionState.CREATED, TransactionState.CLAIMED, TransactionState.PROCESSING, TransactionState.VALIDATED}:
            errors = _restore_sources_from_payload(context, payload)
            try:
                staging_root = _journal_project_path(context, payload, "staging_root")
                shutil.rmtree(staging_root, ignore_errors=True)
            except (OSError, ValueError, TransactionError) as exc:
                errors.append(f"staging cleanup: {exc}")
            payload["state"] = TransactionState.ROLLED_BACK.value
            payload["recovery"] = "restored pre-commit sources"
            payload["updated_at"] = _utc_now_iso()
            if errors:
                payload.setdefault("warnings", []).extend(errors)
            atomic_write_json(journal_path, payload)
            message = "Restored pre-commit source(s)" if not errors else f"Recovery needs attention: {', '.join(errors)}"
            results.append(RecoveryResult(journal_path, "restore", TransactionState.ROLLED_BACK, message))
        elif state is TransactionState.COMMITTED:
            try:
                final_workspace = _journal_project_path(context, payload, "final_workspace")
                if not final_workspace.is_dir():
                    raise TransactionError("Committed final workspace is missing")
            except (OSError, ValueError, TransactionError) as exc:
                message = f"Recovery needs attention: {exc}"
                payload.setdefault("warnings", []).append(message)
                payload["updated_at"] = _utc_now_iso()
                atomic_write_json(journal_path, payload)
                results.append(RecoveryResult(journal_path, "resume", TransactionState.COMMITTED, message))
                continue
            errors = _materialize_and_archive_from_payload(context, payload)
            if errors:
                payload.setdefault("warnings", []).extend(errors)
                payload["updated_at"] = _utc_now_iso()
                atomic_write_json(journal_path, payload)
                results.append(RecoveryResult(journal_path, "resume", TransactionState.COMMITTED, "; ".join(errors)))
            else:
                payload["state"] = TransactionState.ARCHIVED.value
                payload["recovery"] = "finished committed transaction archival"
                payload["updated_at"] = _utc_now_iso()
                atomic_write_json(journal_path, payload)
                staging_root = _journal_project_path(context, payload, "staging_root")
                shutil.rmtree(staging_root, ignore_errors=True)
                results.append(RecoveryResult(journal_path, "resume", TransactionState.ARCHIVED, "Finished archival"))
    return results


def process_video_transaction(transaction: ProcessingTransaction, api) -> dict[str, Any]:
    """Process one claimed video without writing user-visible output before commit."""

    claim = transaction.claims[0]
    frame_paths: list[Path] = []
    try:
        workspace, working_sources = transaction.start(build_post_id("video", [claim.original_path]))
        source = working_sources[0]
        api.check_cancelled()
        frame_paths = extract_video_frames(source, transaction.staging_root / "frames", cancellation_check=api.check_cancelled)
        transaction._checkpoint("after_frame_extraction")
        prompt = (
            f"{api.PROMPT_TEMPLATE}\n"
            f"Filename context: {claim.original_path.name}\n"
            f"Normalized filename hints: {api.build_filename_context([claim.original_path])}\n"
            "The attached frames come from the same commercial. Use them together to infer the product, era, and selling angle."
        )
        meta, analysis_source, analysis_error = api.analyze_with_fallback(
            prompt,
            frame_paths,
            api.infer_meta_from_filename(claim.original_path),
        )
        transaction._checkpoint("after_analysis")
        api.check_cancelled()
        if meta is None:
            raise TransactionError(analysis_error or "AI analysis failed")

        caption_payload = api.build_caption_payload(meta, claim.original_path.name)
        caption_text = api.build_caption_block(meta, claim.original_path.name)
        staged_processed = transaction.staged_processed_path(f"{source.stem}.mp4")
        if not convert_video_to_vertical(source, staged_processed, cancellation_check=api.check_cancelled):
            raise TransactionError("Video conversion did not produce a valid staged output")
        transaction._checkpoint("after_video_conversion")
        transaction.register_processed_artifact(staged_processed, staged_processed.name)
        workspace_media = transaction.staged_workspace_path(Path("media") / staged_processed.name)
        shutil.copy2(staged_processed, workspace_media)
        caption_path, _ = transaction.write_caption(caption_text, f"{claim.original_path.stem}.txt")
        manifest_path = write_post_manifest(
            post_id=transaction.post_id or "unknown",
            output_dir=workspace,
            post_type="video",
            workflow_status=PublishStatus.READY,
            source_files=[claim.original_path],
            processed_files=[workspace_media],
            caption_text=caption_text,
            title=caption_payload["title"],
            description=caption_payload["description"],
            hashtags=caption_payload["hashtags"],
            details=caption_payload["details"],
            meta=meta,
            analysis_source=analysis_source,
            analysis_error=analysis_error,
            caption_path=caption_path,
            legacy_caption_path=None,
            base_dir=transaction.context.project_dir,
            inbox_dir=transaction.context.inbox_dir,
        )
        transaction.rewrite_manifest_for_final_paths(manifest_path, transaction.context.captions_dir / f"{claim.original_path.stem}.txt")
        transaction.validate(expected_media_count=1)
        outcome = transaction.commit_and_archive()
        return _video_record(transaction, outcome, claim.original_path, meta, analysis_source, analysis_error, len(frame_paths))
    except OperationCancelled:
        transaction.rollback("processing cancelled")
        raise
    except Exception as exc:
        outcome = transaction.rollback(str(exc))
        return {
            "type": "video",
            "file": claim.original_path.name,
            "status": "failed",
            "transaction_status": "failed_before_commit",
            "transaction_id": transaction.transaction_id,
            "error": "transaction_failed",
            "message": str(exc),
            "rollback_warnings": list(outcome.warnings),
        }
    finally:
        cleanup_temp_files(frame_paths, transaction.staging_root / "frames")


def process_image_batch_transaction(transaction: ProcessingTransaction, api) -> dict[str, Any]:
    """Process all claimed images as one all-or-nothing carousel transaction."""

    claims = transaction.claims
    try:
        workspace, working_sources = transaction.start(build_post_id("image-carousel", [claim.original_path for claim in claims]))
        api.check_cancelled()
        filenames_text = "\n".join(f"- {claim.original_path.name}" for claim in claims)
        prompt = (
            f"{api.IMAGE_CAROUSEL_PROMPT_TEMPLATE}\n"
            f"Image filenames in this batch:\n{filenames_text}\n"
            f"Normalized filename hints: {api.build_filename_context([claim.original_path for claim in claims])}\n"
            "Use logos, headlines, prices, platform names, issue branding, and recurring design motifs to make the caption smarter."
        )
        meta, analysis_source, analysis_error = api.analyze_image_batch_with_fallback(
            prompt,
            working_sources,
            api.infer_carousel_meta_from_files([claim.original_path for claim in claims]),
        )
        transaction._checkpoint("after_analysis")
        api.check_cancelled()
        if meta is None:
            raise TransactionError(analysis_error or "AI analysis failed")

        caption_payload = api.build_carousel_caption_payload(meta)
        caption_text = api.build_carousel_caption_block(meta, [claim.original_path for claim in claims])
        staged_processed: list[Path] = []
        workspace_media: list[Path] = []
        for index, source in enumerate(working_sources):
            api.check_cancelled()
            claim = claims[index]
            destination = transaction.staged_processed_path(source.name)
            dimensions = get_media_dimensions(source)
            needs_convert = dimensions != (1080, 1350)
            if needs_convert:
                converted = convert_image_to_instagram(source, destination, cancellation_check=api.check_cancelled)
                if not converted:
                    shutil.copy2(source, destination)
            else:
                shutil.copy2(source, destination)
            transaction.register_processed_artifact(destination, destination.name)
            staged_processed.append(destination)
            media_path = transaction.staged_workspace_path(Path("media") / destination.name)
            shutil.copy2(destination, media_path)
            workspace_media.append(media_path)
            transaction._checkpoint(f"after_image_conversion_{index + 1}")

        carousel_name = f"{transaction.post_id}-carousel-video.mp4"
        staged_carousel = transaction.staged_processed_path(carousel_name)
        if not create_carousel_video_from_images(staged_processed, staged_carousel, cancellation_check=api.check_cancelled):
            raise TransactionError("Carousel slideshow generation did not produce a valid staged output")
        transaction._checkpoint("after_slideshow_generation")
        transaction.register_processed_artifact(staged_carousel, staged_carousel.name)
        carousel_workspace = transaction.staged_workspace_path(Path("tiktok") / "media" / staged_carousel.name)
        shutil.copy2(staged_carousel, carousel_workspace)
        caption_path, _ = transaction.write_caption(caption_text, f"carousel-{transaction.post_id}.txt")
        manifest_path = write_post_manifest(
            post_id=transaction.post_id or "unknown",
            output_dir=workspace,
            post_type="image_carousel",
            workflow_status=PublishStatus.READY,
            source_files=[claim.original_path for claim in claims],
            processed_files=[*workspace_media, carousel_workspace],
            caption_text=caption_text,
            title=caption_payload["title"],
            description=caption_payload["description"],
            hashtags=caption_payload["hashtags"],
            details=caption_payload["details"],
            meta=meta,
            analysis_source=analysis_source,
            analysis_error=analysis_error,
            caption_path=caption_path,
            legacy_caption_path=None,
            base_dir=transaction.context.project_dir,
            inbox_dir=transaction.context.inbox_dir,
        )
        transaction.rewrite_manifest_for_final_paths(
            manifest_path,
            transaction.context.captions_dir / f"carousel-{transaction.post_id}.txt",
        )
        transaction.validate(expected_media_count=len(claims) + 1)
        outcome = transaction.commit_and_archive()
        return _carousel_record(transaction, outcome, claims, meta, analysis_source, analysis_error)
    except OperationCancelled:
        transaction.rollback("processing cancelled")
        raise
    except Exception as exc:
        outcome = transaction.rollback(str(exc))
        return {
            "type": "image_carousel",
            "status": "failed",
            "transaction_status": "failed_before_commit",
            "transaction_id": transaction.transaction_id,
            "error": "transaction_failed",
            "message": str(exc),
            "file_count": len(claims),
            "files": [claim.original_path.name for claim in claims],
            "rollback_warnings": list(outcome.warnings),
        }


def _video_record(
    transaction: ProcessingTransaction,
    outcome: TransactionResult,
    source: Path,
    meta: dict[str, Any],
    analysis_source: str,
    analysis_error: str | None,
    frames_used: int,
) -> dict[str, Any]:
    warning = not outcome.fully_completed
    workspace = outcome.final_workspace
    return {
        "type": "video",
        "file": source.name,
        "status": "committed_with_archival_warning" if warning else "processed",
        "transaction_status": outcome.state.value,
        "transaction_id": outcome.transaction_id,
        "caption_path": str(workspace / "caption.txt") if workspace else None,
        "legacy_caption_path": str(transaction.context.captions_dir / f"{source.stem}.txt"),
        "output_dir": str(workspace) if workspace else None,
        "manifest_path": str(workspace / "post_manifest.json") if workspace else None,
        "processed_media_path": str(transaction.context.processed_dir / f"{source.stem}.mp4"),
        "brand": meta.get("brand"),
        "decade": meta.get("decade"),
        "year": meta.get("year"),
        "analysis_source": analysis_source,
        "analysis_error": analysis_error,
        "frames_used": frames_used,
        "publish_status": PublishStatus.READY.value,
        "providers": transaction.context.settings.default_providers,
        "warnings": list(outcome.warnings),
    }


def _carousel_record(
    transaction: ProcessingTransaction,
    outcome: TransactionResult,
    claims: Sequence[InboxClaim],
    meta: dict[str, Any],
    analysis_source: str,
    analysis_error: str | None,
) -> dict[str, Any]:
    warning = not outcome.fully_completed
    workspace = outcome.final_workspace
    return {
        "type": "image_carousel",
        "status": "committed_with_archival_warning" if warning else "processed",
        "transaction_status": outcome.state.value,
        "transaction_id": outcome.transaction_id,
        "file_count": len(claims),
        "files": [claim.original_path.name for claim in claims],
        "caption_path": str(workspace / "caption.txt") if workspace else None,
        "legacy_caption_path": str(transaction.context.captions_dir / f"carousel-{transaction.post_id}.txt"),
        "output_dir": str(workspace) if workspace else None,
        "manifest_path": str(workspace / "post_manifest.json") if workspace else None,
        "processed_media_paths": [
            str(transaction.context.processed_dir / artifact["destination_name"])
            for artifact in transaction.external_artifacts
            if artifact["destination_role"] == "processed"
        ],
        "brand": meta.get("brand"),
        "decade": meta.get("decade"),
        "year": meta.get("year"),
        "analysis_source": analysis_source,
        "analysis_error": analysis_error,
        "publish_status": PublishStatus.READY.value,
        "providers": transaction.context.settings.default_providers,
        "warnings": list(outcome.warnings),
    }


def _restore_sources_from_payload(context: AppContext, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for record in payload.get("sources", []):
        try:
            original = resolve_output_under(context.inbox_dir, str(record["original_relative_path"]))
            claimed = resolve_output_under(context.inbox_dir, str(record["claimed_relative_path"]))
            if claimed.exists() and original.exists():
                errors.append(f"{record.get('original_name') or 'unknown source'} (duplicate claim)")
                continue
            if claimed.exists():
                os.rename(claimed, original)
            if not original.exists() or _sha256(original) != _sha256_from_journal(record):
                errors.append(str(record.get("original_name") or "unknown source"))
        except (OSError, ValueError):
            errors.append(str(record.get("original_name") or "unknown source"))
    return errors


def _materialize_and_archive_from_payload(context: AppContext, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    staging_root = _journal_project_path(context, payload, "staging_root")
    for artifact in payload.get("external_artifacts", []):
        try:
            stage = resolve_existing_under(staging_root, staging_root / str(artifact["stage_relative_path"]))
            role = artifact.get("destination_role")
            if role == "processed":
                root = context.processed_dir
            elif role == "captions":
                root = context.captions_dir
            else:
                raise TransactionError(f"Unsupported external artifact role: {role}")
            destination = resolve_output_under(root, str(artifact["destination_name"]))
            _atomic_copy(stage, destination)
        except (OSError, ValueError):
            errors.append(f"external artifact {artifact.get('destination_name', 'unknown')}")
    archive_dir = context.inbox_dir / ".archive" / str(payload.get("run_id") or "unknown")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for record in payload.get("sources", []):
        try:
            claimed = resolve_output_under(context.inbox_dir, str(record["claimed_relative_path"]))
            archive = resolve_output_under(context.inbox_dir, str(record["archive_relative_path"]))
            if claimed.exists() and not archive.exists():
                archive.parent.mkdir(parents=True, exist_ok=True)
                os.rename(claimed, archive)
            if not archive.exists() or _sha256(archive) != _sha256_from_journal(record):
                errors.append(str(record.get("original_name") or "unknown source"))
        except (OSError, ValueError):
            errors.append(str(record.get("original_name") or "unknown source"))
    return errors


def _journal_project_path(context: AppContext, payload: dict[str, Any], key: str) -> Path:
    paths = payload.get("paths", {})
    if not isinstance(paths, dict) or not paths.get(key):
        raise TransactionError(f"Transaction journal is missing {key}")
    return resolve_output_under(context.project_dir, str(paths[key]))


def _atomic_copy(source: Path, destination: Path) -> None:
    source = Path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != source.stat().st_size:
            raise TransactionError(f"Copied artifact size mismatch: {destination.name}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _relative_or_absolute(project_dir: Path, path: Path) -> str:
    try:
        return normalize_relative_to(project_dir, path)
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_if_exists(path: Path) -> str | None:
    return _sha256(path) if path.exists() else None


def _sha256_from_journal(record: dict[str, Any]) -> str:
    digest = record.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise TransactionError("Transaction journal source hash is missing or invalid")
    return digest


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
