from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from media_rules import is_supported_media_file, unique_destination
except ImportError:
    from scripts.media_rules import is_supported_media_file, unique_destination

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under

try:
    from publishing import load_manifest
except ImportError:
    from scripts.publishing import load_manifest


@dataclass(frozen=True)
class RequeueExecutionResult:
    moved_count: int
    removed_captions: int
    removed_workspaces: int


def build_requeue_confirmation(plan) -> str:
    return (
        f"Move {len(plan.all_files)} file(s) from processed outputs back to inbox?\n\n"
        f"Output workspaces: {len(plan.output_folders)}\n"
        f"Legacy processed files: {len(plan.processed_files)}\n"
        f"Videos: {len(plan.video_files)}\n"
        f"Images: {len(plan.image_files)}\n\n"
        "Matching caption exports and manifest folders will be removed so the next run can regenerate them cleanly."
    )


def execute_requeue_plan(
    plan,
    inbox_dir: Path,
    captions_dir: Path,
    base_dir: Path,
    processed_dir: Path | None = None,
) -> RequeueExecutionResult:
    outputs_dir = resolve_existing_under(base_dir / "outputs", base_dir / "outputs")
    inbox_dir = resolve_existing_under(inbox_dir, inbox_dir)
    captions_dir = resolve_existing_under(captions_dir, captions_dir)
    processed_dir = resolve_existing_under(processed_dir or (base_dir / "!processed"), processed_dir or (base_dir / "!processed"))
    moved = 0
    removed_captions = 0
    removed_workspaces = 0
    output_media_to_move = set(plan.output_media_files)

    for raw_folder in plan.output_folders:
        folder = resolve_existing_under(outputs_dir, raw_folder)
        media_dir = folder / "media"
        media_files = []
        if media_dir.exists():
            media_dir = resolve_existing_under(folder, media_dir)
            media_files = [resolve_existing_under(folder, path) for path in media_dir.iterdir() if path.is_file() and is_supported_media_file(path)]

        manifest_path = resolve_existing_under(folder, folder / "post_manifest.json")
        try:
            manifest = load_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not validate workspace manifest: {exc}") from exc
        _validate_manifest(manifest, base_dir, captions_dir)

        for source in media_files:
            if source not in output_media_to_move:
                continue
            source = resolve_existing_under(folder, source)
            destination = unique_destination(resolve_output_under(inbox_dir, require_plain_filename(source.name)))
            destination = resolve_output_under(inbox_dir, destination)
            shutil.move(str(source), destination)
            moved += 1

        caption_path = resolve_output_under(folder, "caption.txt")
        if caption_path.exists():
            resolve_existing_under(folder, caption_path).unlink()

        legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
        if legacy_caption_path:
            legacy_caption = _resolve_legacy_caption_path(base_dir, captions_dir, str(legacy_caption_path))
            if legacy_caption.exists():
                resolve_existing_under(captions_dir, legacy_caption).unlink()
                removed_captions += 1

        shutil.rmtree(resolve_existing_under(outputs_dir, folder))
        removed_workspaces += 1

    for raw_source in plan.processed_files:
        source = resolve_existing_under(processed_dir, raw_source)
        destination = unique_destination(resolve_output_under(inbox_dir, require_plain_filename(source.name)))
        destination = resolve_output_under(inbox_dir, destination)
        shutil.move(str(source), destination)
        moved += 1

        per_file_caption = resolve_output_under(captions_dir, require_plain_filename(f"{source.stem}.txt"))
        if per_file_caption.exists():
            resolve_existing_under(captions_dir, per_file_caption).unlink()
            removed_captions += 1

    return RequeueExecutionResult(
        moved_count=moved,
        removed_captions=removed_captions,
        removed_workspaces=removed_workspaces,
    )


def _validate_manifest(manifest: dict, base_dir: Path, captions_dir: Path) -> None:
    for item in manifest.get("media_files", []):
        if isinstance(item, dict) and item.get("filename"):
            require_plain_filename(str(item["filename"]))
    legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
    if legacy_caption_path:
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
