#!/usr/bin/env python3
"""Create complete, independently verifiable manual publishing packs.

The final pack is never used as a workspace.  Every source is preflighted,
then copied into a unique sibling directory, hashed, and verified before that
directory replaces the previous pack.  If staging fails, the previous pack is
left alone.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from atomic_io import InvalidSchemaError, atomic_write_json, atomic_write_text, load_json, require_json_object
except ImportError:
    from scripts.atomic_io import InvalidSchemaError, atomic_write_json, atomic_write_text, load_json, require_json_object

try:
    from platform_profiles import get_platform_profile
except ImportError:
    from scripts.platform_profiles import get_platform_profile

try:
    from publishing import format_hashtag_block, load_manifest
except ImportError:
    from scripts.publishing import format_hashtag_block, load_manifest

try:
    from readiness import format_readiness_report, format_readiness_reports, readiness_reports_for_manifest, render_final_caption, require_ready_reports
except ImportError:
    from scripts.readiness import format_readiness_report, format_readiness_reports, readiness_reports_for_manifest, render_final_caption, require_ready_reports

try:
    from safe_paths import UnsafePathError, normalize_relative_to, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, normalize_relative_to, require_plain_filename, resolve_existing_under, resolve_output_under


INTEGRITY_SCHEMA_VERSION = 1
PLATFORM_PROFILE_VERSION = 1


class PostingPackExportError(RuntimeError):
    """Raised when a complete posting pack cannot be created safely."""


class PostingPackIntegrityError(PostingPackExportError):
    """Raised when a staged or existing pack does not match its integrity manifest."""


@dataclass(frozen=True)
class PostingPackResult:
    pack_dir: Path
    media_count: int
    caption_path: Path
    notes_path: Path
    hashtags_path: Path
    integrity_path: Path


@dataclass(frozen=True)
class _MediaSource:
    order: int
    source: Path
    source_relative_path: str
    output_name: str
    byte_size: int
    sha256: str


def create_posting_pack(
    manifest_path: Path,
    exports_dir: Path,
    platforms: tuple[str, ...] = ("manual_export", "instagram", "facebook"),
    *,
    captions_root: Path | None = None,
) -> PostingPackResult:
    """Create a verified pack, leaving any previous pack untouched on failure.

    ``captions_root`` remains accepted for desktop-call compatibility.  A pack
    always uses the exact caption rendered from the saved manifest rather than
    a separate caption export that could be stale.
    """

    del captions_root
    manifest_path, outputs_root, project_root = _manifest_context(manifest_path)
    manifest = load_manifest(manifest_path)
    post_id = str(manifest.get("post_id") or manifest_path.parent.name)
    safe_post_id = _safe_folder_name(post_id)
    safe_platforms = _validated_platforms(platforms)
    media_sources = _preflight_media_sources(manifest, manifest_path, project_root)
    if not media_sources:
        raise PostingPackExportError("Cannot export a posting pack without media files")
    readiness_reports = readiness_reports_for_manifest(manifest_path, safe_platforms, manifest=manifest)
    require_ready_reports(readiness_reports)
    caption_text = render_final_caption(manifest)

    # The export root is a runtime-controlled destination.  No directory below
    # it is created until every manifest-derived input has passed preflight.
    export_root = Path(exports_dir)
    export_root.mkdir(parents=True, exist_ok=True)
    export_root = export_root.resolve(strict=True)
    if not export_root.is_dir():
        raise PostingPackExportError(f"Export root is not a directory: {export_root}")
    packs_root = resolve_output_under(export_root, "posting-packs")
    packs_root.mkdir(parents=True, exist_ok=True)
    packs_root = resolve_existing_under(export_root, packs_root)
    pack_dir = resolve_output_under(packs_root, safe_post_id)

    staging_dir = Path(tempfile.mkdtemp(prefix=f".{safe_post_id}.", suffix=".tmp", dir=packs_root))
    staging_dir = resolve_existing_under(packs_root, staging_dir)
    try:
        _build_staged_pack(
            staging_dir,
            manifest_path=manifest_path,
            outputs_root=outputs_root,
            project_root=project_root,
            manifest=manifest,
            post_id=post_id,
            caption_text=caption_text,
            readiness_reports=readiness_reports,
            media_sources=media_sources,
        )
        verify_posting_pack(staging_dir)
        _replace_verified_pack(staging_dir, pack_dir, packs_root)
    except Exception:
        _remove_directory_if_present(staging_dir, packs_root)
        raise

    final_pack = resolve_existing_under(packs_root, pack_dir)
    return _result_for_pack(final_pack, media_count=len(media_sources))


def verify_posting_pack(pack_dir: Path) -> dict[str, Any]:
    """Validate a completed pack against its stored file count and SHA-256s."""

    root = Path(pack_dir).resolve(strict=True)
    if not root.is_dir():
        raise PostingPackIntegrityError(f"Posting pack is not a directory: {root}")
    integrity_path = resolve_existing_under(root, root / "pack-integrity.json")
    try:
        payload = require_json_object(load_json(integrity_path, document_name="Posting-pack integrity manifest"), document_name="Posting-pack integrity manifest")
    except InvalidSchemaError as exc:
        raise PostingPackIntegrityError(str(exc)) from exc
    if payload.get("schema_version") != INTEGRITY_SCHEMA_VERSION:
        raise PostingPackIntegrityError(
            f"Posting-pack integrity manifest uses unsupported schema_version {payload.get('schema_version')!r}"
        )
    _verify_platform_profiles(payload.get("platform_profiles"))
    expected_files = _required_list(payload, "files")
    expected_count = _required_nonnegative_int(payload, "file_count")
    if expected_count != len(expected_files):
        raise PostingPackIntegrityError(
            f"Integrity manifest expects {expected_count} files but lists {len(expected_files)}"
        )

    expected_by_path: dict[str, dict[str, Any]] = {}
    for entry in expected_files:
        if not isinstance(entry, dict):
            raise PostingPackIntegrityError("Integrity manifest file entries must be objects")
        relative_path = _required_relative_path(entry, "path")
        if relative_path in expected_by_path:
            raise PostingPackIntegrityError(f"Integrity manifest lists the same file twice: {relative_path}")
        expected_by_path[relative_path] = entry

    actual_paths = {path for path, _ in _pack_files(root)}
    if actual_paths != set(expected_by_path):
        missing = sorted(set(expected_by_path) - actual_paths)
        unexpected = sorted(actual_paths - set(expected_by_path))
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {', '.join(unexpected)}")
        raise PostingPackIntegrityError(f"Posting-pack file set does not match integrity manifest ({'; '.join(details)})")

    for relative_path, entry in expected_by_path.items():
        path = resolve_existing_under(root, relative_path)
        if not path.is_file():
            raise PostingPackIntegrityError(f"Posting-pack entry is not a regular file: {relative_path}")
        expected_size = _required_nonnegative_int(entry, "byte_size")
        if path.stat().st_size != expected_size:
            raise PostingPackIntegrityError(f"Size mismatch for {relative_path}")
        expected_hash = _required_sha256(entry)
        if _sha256(path) != expected_hash:
            raise PostingPackIntegrityError(f"SHA-256 mismatch for {relative_path}")

    _verify_media_entries(payload, expected_by_path)
    return payload


def _build_staged_pack(
    staging_dir: Path,
    *,
    manifest_path: Path,
    outputs_root: Path,
    project_root: Path,
    manifest: dict[str, Any],
    post_id: str,
    caption_text: str,
    readiness_reports: Iterable[Any],
    media_sources: tuple[_MediaSource, ...],
) -> PostingPackResult:
    media_dir = resolve_output_under(staging_dir, "media")
    media_dir.mkdir(parents=True, exist_ok=True)
    media_dir = resolve_existing_under(staging_dir, media_dir)

    caption_path = resolve_output_under(staging_dir, "caption.txt")
    atomic_write_text(caption_path, caption_text)
    hashtags_path = resolve_output_under(staging_dir, "hashtags.txt")
    atomic_write_text(hashtags_path, format_hashtag_block(manifest.get("content", {}).get("hashtags", [])) + "\n")
    notes_path = resolve_output_under(staging_dir, "posting-notes.txt")
    atomic_write_text(notes_path, _posting_notes(manifest))
    _write_platform_files(staging_dir, caption_text, readiness_reports)

    manifest_destination = resolve_output_under(staging_dir, "post_manifest.json")
    shutil.copy2(resolve_existing_under(outputs_root, manifest_path), manifest_destination)
    for media in media_sources:
        destination = resolve_output_under(media_dir, media.output_name)
        shutil.copy2(media.source, destination)
        if destination.stat().st_size != media.byte_size or _sha256(destination) != media.sha256:
            raise PostingPackIntegrityError(f"Copied media did not match preflighted source: {media.source.name}")

    integrity_path = resolve_output_under(staging_dir, "pack-integrity.json")
    integrity_payload = _integrity_payload(
        staging_dir,
        post_id=post_id,
        source_manifest=normalize_relative_to(project_root, manifest_path),
        readiness_reports=readiness_reports,
        media_sources=media_sources,
    )
    atomic_write_json(integrity_path, integrity_payload)
    return PostingPackResult(
        pack_dir=staging_dir,
        media_count=len(media_sources),
        caption_path=caption_path,
        notes_path=notes_path,
        hashtags_path=hashtags_path,
        integrity_path=integrity_path,
    )


def _preflight_media_sources(manifest: dict[str, Any], manifest_path: Path, project_root: Path) -> tuple[_MediaSource, ...]:
    raw_sources = _media_sources(manifest, manifest_path, project_root)
    if not raw_sources:
        return ()
    output_names = _collision_safe_names(raw_sources)
    result: list[_MediaSource] = []
    for order, (source, output_name) in enumerate(zip(raw_sources, output_names), start=1):
        safe_source = resolve_existing_under(project_root, source)
        if not safe_source.is_file():
            raise PostingPackExportError(f"Manifest media entry is not a regular file: {safe_source}")
        try:
            byte_size = safe_source.stat().st_size
            digest = _sha256(safe_source)
        except OSError as exc:
            raise PostingPackExportError(f"Could not read manifest media file: {safe_source}") from exc
        result.append(
            _MediaSource(
                order=order,
                source=safe_source,
                source_relative_path=normalize_relative_to(project_root, safe_source),
                output_name=output_name,
                byte_size=byte_size,
                sha256=digest,
            )
        )
    return tuple(result)


def _media_sources(manifest: dict[str, Any], manifest_path: Path, project_root: Path) -> list[Path]:
    sources: list[Path] = []
    for index, item in enumerate(manifest.get("media_files", []), start=1):
        if not isinstance(item, dict):
            raise PostingPackExportError(f"Manifest media entry {index} is not an object")
        resolved = _resolve_manifest_path(item.get("relative_path"), project_root)
        if resolved is not None:
            sources.append(resolved)
            continue
        filename = item.get("filename")
        if not filename:
            raise PostingPackExportError(f"Manifest media entry {index} has no source path or filename")
        sources.append(resolve_existing_under(manifest_path.parent / "media", require_plain_filename(str(filename))))
    return sources


def _resolve_manifest_path(raw_path: Any, project_root: Path) -> Path | None:
    if not raw_path:
        return None
    return resolve_existing_under(project_root, str(raw_path))


def _collision_safe_names(sources: list[Path]) -> tuple[str, ...]:
    bases = [require_plain_filename(source.name) for source in sources]
    counts = {name: bases.count(name) for name in bases}
    used: set[str] = set()
    result: list[str] = []
    for order, base in enumerate(bases, start=1):
        candidate = base if counts[base] == 1 else _ordered_media_name(order, base)
        attempt = 2
        while candidate.lower() in used:
            candidate = _ordered_media_name(order, base, attempt=attempt)
            attempt += 1
        used.add(candidate.lower())
        result.append(candidate)
    return tuple(result)


def _ordered_media_name(order: int, base: str, *, attempt: int | None = None) -> str:
    path = Path(base)
    suffix = path.suffix
    stem = path.stem or "media"
    suffix_part = f"-{attempt}" if attempt is not None else ""
    return f"{order:02d}-{stem}{suffix_part}{suffix}"


def _validated_platforms(platforms: Iterable[str]) -> tuple[str, ...]:
    selected: list[str] = []
    for raw_platform in platforms:
        platform = require_plain_filename(str(raw_platform).strip())
        if get_platform_profile(platform) is None:
            raise PostingPackExportError(f"Unknown export platform: {platform}")
        if platform not in selected:
            selected.append(platform)
    if not selected:
        raise PostingPackExportError("Choose at least one export platform")
    return tuple(selected)


def _write_platform_files(pack_dir: Path, caption_text: str, reports: Iterable[Any]) -> None:
    platform_dir = resolve_output_under(pack_dir, "platforms")
    platform_dir.mkdir(parents=True, exist_ok=True)
    platform_dir = resolve_existing_under(pack_dir, platform_dir)
    atomic_write_text(resolve_output_under(platform_dir, "platform-validation.txt"), format_readiness_reports(reports))
    for report in reports:
        platform_name = require_plain_filename(report.platform)
        atomic_write_text(resolve_output_under(platform_dir, f"{platform_name}-caption.txt"), caption_text)
        atomic_write_text(resolve_output_under(platform_dir, f"{platform_name}-notes.txt"), format_readiness_report(report))


def _integrity_payload(
    pack_dir: Path,
    *,
    post_id: str,
    source_manifest: str,
    readiness_reports: Iterable[Any],
    media_sources: tuple[_MediaSource, ...],
) -> dict[str, Any]:
    files = [
        {"path": relative_path, "byte_size": path.stat().st_size, "sha256": _sha256(path)}
        for relative_path, path in _pack_files(pack_dir)
    ]
    by_path = {entry["path"]: entry for entry in files}
    media = []
    for source in media_sources:
        relative_path = f"media/{source.output_name}"
        copied = by_path[relative_path]
        media.append(
            {
                "order": source.order,
                "filename": source.output_name,
                "path": relative_path,
                "byte_size": copied["byte_size"],
                "sha256": copied["sha256"],
                "source_path": source.source_relative_path,
            }
        )
    return {
        "schema_version": INTEGRITY_SCHEMA_VERSION,
        "post_id": post_id,
        "source_manifest": source_manifest,
        "platform_profiles": [
            {"name": report.platform, "version": PLATFORM_PROFILE_VERSION} for report in readiness_reports
        ],
        "file_count": len(files),
        "files": files,
        "media_count": len(media),
        "media": media,
    }


def _pack_files(pack_dir: Path) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for path in sorted(pack_dir.rglob("*")):
        if path.name == "pack-integrity.json":
            continue
        if path.is_symlink():
            raise PostingPackIntegrityError(f"Posting pack contains a symlink: {path.name}")
        if path.is_file():
            resolved = resolve_existing_under(pack_dir, path)
            result.append((resolved.relative_to(pack_dir.resolve()).as_posix(), resolved))
    return result


def _replace_verified_pack(staging_dir: Path, pack_dir: Path, packs_root: Path) -> None:
    """Publish a staged directory and restore the old one if its swap fails."""

    if not pack_dir.exists():
        os.replace(staging_dir, pack_dir)
        return
    existing_pack = resolve_existing_under(packs_root, pack_dir)
    if not existing_pack.is_dir():
        raise PostingPackExportError(f"Existing posting pack is not a directory: {existing_pack}")
    backup_dir = resolve_output_under(packs_root, f".{pack_dir.name}.backup-{uuid.uuid4().hex}")
    try:
        os.replace(existing_pack, backup_dir)
    except OSError as exc:
        raise PostingPackExportError(f"Could not prepare existing posting pack for replacement: {existing_pack}") from exc
    try:
        os.replace(staging_dir, pack_dir)
    except OSError as exc:
        try:
            os.replace(backup_dir, pack_dir)
        except OSError as rollback_exc:
            raise PostingPackExportError(
                f"Could not replace posting pack; previous pack remains at recoverable path {backup_dir}"
            ) from rollback_exc
        raise PostingPackExportError("Could not replace posting pack; the previous pack was restored") from exc
    # The new pack is already complete and verified.  A locked old backup is
    # recoverable housekeeping, not a reason to report the successful export
    # as failed or to attempt a dangerous second swap.
    try:
        _remove_directory_if_present(backup_dir, packs_root)
    except OSError:
        pass


def _remove_directory_if_present(path: Path, root: Path) -> None:
    if not path.exists():
        return
    try:
        safe_path = resolve_existing_under(root, path)
    except UnsafePathError:
        return
    if safe_path.is_dir():
        shutil.rmtree(safe_path)


def _result_for_pack(pack_dir: Path, *, media_count: int) -> PostingPackResult:
    return PostingPackResult(
        pack_dir=pack_dir,
        media_count=media_count,
        caption_path=resolve_existing_under(pack_dir, "caption.txt"),
        notes_path=resolve_existing_under(pack_dir, "posting-notes.txt"),
        hashtags_path=resolve_existing_under(pack_dir, "hashtags.txt"),
        integrity_path=resolve_existing_under(pack_dir, "pack-integrity.json"),
    )


def _verify_platform_profiles(raw_profiles: Any) -> None:
    profiles = _required_list({"profiles": raw_profiles}, "profiles")
    if not profiles:
        raise PostingPackIntegrityError("Integrity manifest does not list any platform profiles")
    for entry in profiles:
        if not isinstance(entry, dict):
            raise PostingPackIntegrityError("Integrity manifest platform profile entries must be objects")
        name = entry.get("name")
        if not isinstance(name, str) or get_platform_profile(name) is None:
            raise PostingPackIntegrityError(f"Integrity manifest has an unknown platform profile: {name!r}")
        if entry.get("version") != PLATFORM_PROFILE_VERSION:
            raise PostingPackIntegrityError(f"Unsupported platform profile version for {name}")


def _verify_media_entries(payload: dict[str, Any], expected_by_path: dict[str, dict[str, Any]]) -> None:
    media_entries = _required_list(payload, "media")
    if _required_nonnegative_int(payload, "media_count") != len(media_entries):
        raise PostingPackIntegrityError("Integrity manifest media count does not match its media list")
    if not media_entries:
        raise PostingPackIntegrityError("Integrity manifest does not list any media")
    for expected_order, entry in enumerate(media_entries, start=1):
        if not isinstance(entry, dict):
            raise PostingPackIntegrityError("Integrity manifest media entries must be objects")
        if entry.get("order") != expected_order:
            raise PostingPackIntegrityError("Integrity manifest media entries are not in upload order")
        relative_path = _required_relative_path(entry, "path")
        file_entry = expected_by_path.get(relative_path)
        if file_entry is None:
            raise PostingPackIntegrityError(f"Integrity manifest media entry is missing from files: {relative_path}")
        if entry.get("filename") != Path(relative_path).name:
            raise PostingPackIntegrityError(f"Integrity manifest media filename does not match its path: {relative_path}")
        if entry.get("byte_size") != file_entry.get("byte_size") or entry.get("sha256") != file_entry.get("sha256"):
            raise PostingPackIntegrityError(f"Integrity manifest media values do not match file values: {relative_path}")


def _required_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise PostingPackIntegrityError(f"Integrity manifest {key} must be a list")
    return value


def _required_nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PostingPackIntegrityError(f"Integrity manifest {key} must be a non-negative integer")
    return value


def _required_relative_path(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise PostingPackIntegrityError(f"Integrity manifest {key} must be a non-empty path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PostingPackIntegrityError(f"Integrity manifest {key} must stay inside the pack")
    return value.replace("\\", "/")


def _required_sha256(entry: dict[str, Any]) -> str:
    value = entry.get("sha256")
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise PostingPackIntegrityError("Integrity manifest sha256 must be a lowercase hexadecimal SHA-256")
    return value.lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _posting_notes(manifest: dict[str, Any]) -> str:
    content = manifest.get("content", {})
    publishing = manifest.get("publishing", {})
    providers = publishing.get("selected_providers", [])
    lines = [
        f"Title: {content.get('title', '')}",
        f"Post ID: {manifest.get('post_id', '')}",
        f"Type: {manifest.get('post_type', '')}",
        f"Status: {publishing.get('workflow_status', '')}",
        f"Destinations: {', '.join(providers) if providers else 'manual_export'}",
        "",
        "Use caption.txt for the post body and media/ for upload assets.",
    ]
    return "\n".join(lines) + "\n"


def _safe_folder_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
    return cleaned.strip("-") or "post"


def _manifest_context(manifest_path: Path) -> tuple[Path, Path, Path]:
    raw_path = Path(manifest_path)
    if raw_path.name != "post_manifest.json":
        raise UnsafePathError("Posting-pack export requires a post_manifest.json file")
    outputs_root = raw_path.parent.parent
    project_root = outputs_root.parent
    safe_manifest = resolve_existing_under(outputs_root, raw_path)
    if safe_manifest.parent.parent != outputs_root.resolve():
        raise UnsafePathError("Posting-pack export requires a direct output workspace manifest")
    return safe_manifest, outputs_root.resolve(), project_root.resolve()
