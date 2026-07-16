#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from media_rules import is_supported_media_file, split_media_files, unique_destination
except ImportError:
    from scripts.media_rules import is_supported_media_file, split_media_files, unique_destination


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
    output_folders = [path for path in outputs_dir.iterdir() if path.is_dir() and (path / "post_manifest.json").exists()]
    generated_names = _generated_media_names(output_folders)
    processed_files = [
        path
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
        for path in media_dir.iterdir():
            if not path.is_file() or not is_supported_media_file(path):
                continue
            key = path.name.lower()
            if key in seen_output_names:
                continue
            seen_output_names.add(key)
            output_media_files.append(path)

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
        records = json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        records = []

    retry_files: list[Path] = []
    missing: list[str] = []
    seen: set[str] = set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or str(record.get("status", "")).lower() != "failed":
            continue
        for name in _record_file_names(record):
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            candidate = inbox_dir / name
            if candidate.exists():
                retry_files.append(candidate)
            else:
                missing.append(name)
    return FailedRunRetryPlan(retry_files=tuple(retry_files), missing_files=tuple(missing))


def requeue_output_workspace(
    workspace_dir: Path,
    inbox_dir: Path,
    processed_dir: Path,
    base_dir: Path,
) -> WorkspaceRequeueResult:
    manifest_path = workspace_dir / "post_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}

    moved_files: list[Path] = []
    removed_caption_paths: list[Path] = []
    _delete_generated_workspace_media(workspace_dir, processed_dir, manifest)
    for source in _workspace_media_sources(workspace_dir, processed_dir, manifest):
        if not source.exists():
            continue
        destination = unique_destination(inbox_dir / source.name)
        shutil.move(str(source), destination)
        moved_files.append(destination)

    for caption_path in _workspace_caption_paths(workspace_dir, base_dir, manifest):
        if caption_path.exists():
            caption_path.unlink()
            removed_caption_paths.append(caption_path)

    shutil.rmtree(workspace_dir, ignore_errors=True)
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
            names.append(str(item["filename"]))

    media_dir = workspace_dir / "media"
    if not names and media_dir.exists():
        names = [path.name for path in media_dir.iterdir() if path.is_file() and is_supported_media_file(path)]

    sources: list[Path] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        primary = processed_dir / name
        shadow = media_dir / name
        if primary.exists():
            sources.append(primary)
        elif shadow.exists():
            sources.append(shadow)
    return sources


def _generated_media_names(output_folders: list[Path]) -> set[str]:
    names: set[str] = set()
    for folder in output_folders:
        try:
            manifest = json.loads((folder / "post_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in manifest.get("media_files", []):
            if _is_generated_media_item(item) and item.get("filename"):
                names.add(str(item["filename"]).lower())
    return names


def _delete_generated_workspace_media(workspace_dir: Path, processed_dir: Path, manifest: dict) -> None:
    media_dir = workspace_dir / "media"
    for item in manifest.get("media_files", []):
        if not _is_generated_media_item(item) or not item.get("filename"):
            continue
        name = str(item["filename"])
        (processed_dir / name).unlink(missing_ok=True)
        (media_dir / name).unlink(missing_ok=True)


def _is_generated_media_item(item: object) -> bool:
    return isinstance(item, dict) and item.get("role") == "carousel_video"


def _workspace_caption_paths(workspace_dir: Path, base_dir: Path, manifest: dict) -> list[Path]:
    paths = [workspace_dir / "caption.txt"]
    legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
    if legacy_caption_path:
        paths.append(base_dir / str(legacy_caption_path))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve() if path.exists() else path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _record_file_names(record: dict) -> list[str]:
    files = record.get("files")
    if isinstance(files, list):
        return [str(item) for item in files if str(item)]
    if record.get("file"):
        return [str(record["file"])]
    return []
