#!/usr/bin/env python3
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from media_rules import is_supported_media_file, split_media_files, unique_destination
except ImportError:
    from scripts.media_rules import is_supported_media_file, split_media_files, unique_destination

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under

try:
    from publishing import load_manifest
except ImportError:
    from scripts.publishing import load_manifest

try:
    from run_ledger import normalize_run_log
except ImportError:
    from scripts.run_ledger import normalize_run_log

try:
    from workspace_lock import WorkspaceLock
except ImportError:
    from scripts.workspace_lock import WorkspaceLock


@dataclass
class RequeuePlan:
    output_folders: List[Path]
    output_media_files: List[Path]
    processed_files: List[Path]
    all_files: List[Path]
    image_files: List[Path]
    video_files: List[Path]


@dataclass(frozen=True)
class WorkspaceRequeueResult:
    moved_files: tuple[Path, ...]
    removed_workspace: Path
    removed_caption_paths: tuple[Path, ...]


@dataclass(frozen=True)
class FailedRunRetryPlan:
    retry_files: tuple[Path, ...]
    missing_files: tuple[str, ...]


def collect_requeue_plan(outputs_dir: Path, processed_dir: Path) -> RequeuePlan:
    outputs_dir = resolve_existing_under(outputs_dir, outputs_dir)
    processed_dir = resolve_existing_under(processed_dir, processed_dir)
    output_folders = [
        resolve_existing_under(outputs_dir, path)
        for path in outputs_dir.iterdir()
        if path.is_dir() and (path / "post_manifest.json").exists()
    ]
    generated_names = _generated_media_names(output_folders)
    processed_files = [
        resolve_existing_under(processed_dir, path)
        for path in processed_dir.iterdir()
        if path.is_file() and is_supported_media_file(path) and path.name.lower() not in generated_names
    ]
    processed_names = {path.name.lower() for path in processed_files}

    output_media_files: List[Path] = []
    seen_output_names = set(processed_names) | generated_names
    for folder in output_folders:
        media_dir = folder / "media"
        if not media_dir.exists():
            continue
        media_dir = resolve_existing_under(folder, media_dir)
        for path in media_dir.iterdir():
            if not path.is_file() or not is_supported_media_file(path):
                continue
            key = path.name.lower()
            if key in seen_output_names:
                continue
            seen_output_names.add(key)
            output_media_files.append(resolve_existing_under(folder, path))

    all_files = output_media_files + processed_files
    video_files, image_files = split_media_files(all_files)
    return RequeuePlan(
        output_folders=output_folders,
        output_media_files=output_media_files,
        processed_files=processed_files,
        all_files=all_files,
        image_files=image_files,
        video_files=video_files,
    )


def collect_failed_run_retry_plan(log_path: Path, inbox_dir: Path) -> FailedRunRetryPlan:
    try:
        safe_log_path = resolve_existing_under(log_path.parent, log_path)
        records = normalize_run_log(safe_log_path)["records"]
    except (OSError, ValueError, UnsafePathError) as exc:
        raise ValueError(f"Could not read failed-run ledger safely: {exc}") from exc

    retry_files: list[Path] = []
    missing: list[str] = []
    seen: set[str] = set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or str(record.get("status", "")).lower() != "failed":
            continue
        for name in _record_file_names(record):
            name = require_plain_filename(name)
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            candidate = resolve_output_under(inbox_dir, name)
            if candidate.exists():
                retry_files.append(resolve_existing_under(inbox_dir, candidate))
            else:
                missing.append(name)
    return FailedRunRetryPlan(retry_files=tuple(retry_files), missing_files=tuple(missing))


def requeue_output_workspace(
    workspace_dir: Path,
    inbox_dir: Path,
    processed_dir: Path,
    base_dir: Path,
    captions_dir: Path | None = None,
) -> WorkspaceRequeueResult:
    lock_root = resolve_existing_under(base_dir, base_dir)
    with WorkspaceLock(lock_root, "requeue selected post"):
        return _requeue_output_workspace(workspace_dir, inbox_dir, processed_dir, lock_root, captions_dir)


def _requeue_output_workspace(
    workspace_dir: Path,
    inbox_dir: Path,
    processed_dir: Path,
    base_dir: Path,
    captions_dir: Path | None = None,
) -> WorkspaceRequeueResult:
    outputs_dir = base_dir / "outputs"
    workspace_dir = resolve_existing_under(outputs_dir, workspace_dir)
    inbox_dir = resolve_existing_under(inbox_dir, inbox_dir)
    processed_dir = resolve_existing_under(processed_dir, processed_dir)
    captions_candidate = captions_dir or (base_dir / "captions")
    captions_dir = resolve_existing_under(captions_candidate, captions_candidate) if captions_candidate.exists() else None
    manifest_path = resolve_existing_under(workspace_dir, workspace_dir / "post_manifest.json")
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not validate workspace manifest: {exc}") from exc
    _validate_workspace_manifest(manifest, base_dir, captions_dir)

    moved_files: list[Path] = []
    removed_caption_paths: list[Path] = []
    _delete_generated_workspace_media(workspace_dir, processed_dir, manifest)
    for source in _workspace_media_sources(workspace_dir, processed_dir, manifest):
        if not source.exists():
            continue
        source_root = processed_dir if _is_same_or_under(source, processed_dir) else workspace_dir
        source = resolve_existing_under(source_root, source)
        destination = unique_destination(resolve_output_under(inbox_dir, require_plain_filename(source.name)))
        destination = resolve_output_under(inbox_dir, destination)
        shutil.move(str(source), destination)
        moved_files.append(destination)

    for caption_path, caption_root in _workspace_caption_paths(workspace_dir, base_dir, captions_dir, manifest):
        if caption_path.exists():
            safe_caption_path = resolve_existing_under(caption_root, caption_path)
            safe_caption_path.unlink()
            removed_caption_paths.append(safe_caption_path)

    shutil.rmtree(resolve_existing_under(outputs_dir, workspace_dir))
    return WorkspaceRequeueResult(
        moved_files=tuple(moved_files),
        removed_workspace=workspace_dir,
        removed_caption_paths=tuple(removed_caption_paths),
    )


def _workspace_media_sources(workspace_dir: Path, processed_dir: Path, manifest: dict) -> list[Path]:
    names: list[str] = []
    for item in manifest.get("media_files", []):
        if _is_generated_media_item(item):
            continue
        if isinstance(item, dict) and item.get("filename"):
            names.append(require_plain_filename(str(item["filename"])))

    media_dir = workspace_dir / "media"
    if not names and media_dir.exists():
        names = [require_plain_filename(path.name) for path in media_dir.iterdir() if path.is_file() and is_supported_media_file(path)]

    sources: list[Path] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        primary = resolve_output_under(processed_dir, name)
        shadow = resolve_output_under(media_dir, name)
        if primary.exists():
            sources.append(resolve_existing_under(processed_dir, primary))
        elif shadow.exists():
            sources.append(resolve_existing_under(workspace_dir, shadow))
    return sources


def _generated_media_names(output_folders: list[Path]) -> set[str]:
    names: set[str] = set()
    for folder in output_folders:
        manifest = load_manifest(folder / "post_manifest.json")
        for item in manifest.get("media_files", []):
            if _is_generated_media_item(item) and item.get("filename"):
                names.add(require_plain_filename(str(item["filename"])).lower())
    return names


def _delete_generated_workspace_media(workspace_dir: Path, processed_dir: Path, manifest: dict) -> None:
    media_dir = workspace_dir / "media"
    for item in manifest.get("media_files", []):
        if not _is_generated_media_item(item) or not item.get("filename"):
            continue
        name = require_plain_filename(str(item["filename"]))
        processed_path = resolve_output_under(processed_dir, name)
        workspace_path = resolve_output_under(media_dir, name)
        if processed_path.exists():
            resolve_existing_under(processed_dir, processed_path).unlink(missing_ok=True)
        if workspace_path.exists():
            resolve_existing_under(workspace_dir, workspace_path).unlink(missing_ok=True)


def _is_generated_media_item(item: object) -> bool:
    return isinstance(item, dict) and item.get("role") == "carousel_video"


def _workspace_caption_paths(
    workspace_dir: Path,
    base_dir: Path,
    captions_dir: Path | None,
    manifest: dict,
) -> list[tuple[Path, Path]]:
    paths: list[tuple[Path, Path]] = [(resolve_output_under(workspace_dir, "caption.txt"), workspace_dir)]
    legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
    if legacy_caption_path:
        if captions_dir is None:
            raise UnsafePathError("Configured captions root is unavailable for legacy caption cleanup")
        paths.append((_resolve_legacy_caption_path(base_dir, captions_dir, str(legacy_caption_path)), captions_dir))
    unique: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for path, root in paths:
        key = str(path.resolve() if path.exists() else path).lower()
        if key not in seen:
            seen.add(key)
            unique.append((path, root))
    return unique


def _record_file_names(record: dict) -> list[str]:
    files = record.get("files")
    if isinstance(files, list):
        return [str(item) for item in files if str(item)]
    if record.get("file"):
        return [str(record["file"])]
    return []


def _validate_workspace_manifest(manifest: dict, base_dir: Path, captions_dir: Path | None) -> None:
    for item in manifest.get("media_files", []):
        if isinstance(item, dict) and item.get("filename"):
            require_plain_filename(str(item["filename"]))
    legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
    if legacy_caption_path:
        if captions_dir is None:
            raise UnsafePathError("Configured captions root is unavailable for legacy caption cleanup")
        _resolve_legacy_caption_path(base_dir, captions_dir, str(legacy_caption_path))


def _resolve_legacy_caption_path(base_dir: Path, captions_dir: Path, raw_path: str) -> Path:
    try:
        project_candidate = resolve_output_under(base_dir, raw_path)
        try:
            project_candidate.relative_to(captions_dir.resolve())
        except ValueError:
            pass
        else:
            return project_candidate
    except UnsafePathError:
        pass
    return resolve_output_under(captions_dir, raw_path)


def _is_same_or_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
