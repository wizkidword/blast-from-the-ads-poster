from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from media_rules import is_supported_media_file, unique_destination
except ImportError:
    from scripts.media_rules import is_supported_media_file, unique_destination


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


def execute_requeue_plan(plan, inbox_dir: Path, captions_dir: Path, base_dir: Path) -> RequeueExecutionResult:
    moved = 0
    removed_captions = 0
    removed_workspaces = 0
    output_media_to_move = set(plan.output_media_files)

    for folder in plan.output_folders:
        media_dir = folder / "media"
        media_files = []
        if media_dir.exists():
            media_files = [path for path in media_dir.iterdir() if path.is_file() and is_supported_media_file(path)]

        for source in media_files:
            if source not in output_media_to_move:
                continue
            destination = unique_destination(inbox_dir / source.name)
            shutil.move(str(source), destination)
            moved += 1

        caption_path = folder / "caption.txt"
        if caption_path.exists():
            caption_path.unlink()

        manifest_path = folder / "post_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
            legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
            if legacy_caption_path:
                legacy_caption = base_dir / legacy_caption_path
                if legacy_caption.exists():
                    legacy_caption.unlink()
                    removed_captions += 1

        shutil.rmtree(folder, ignore_errors=True)
        removed_workspaces += 1

    for source in plan.processed_files:
        destination = unique_destination(inbox_dir / source.name)
        shutil.move(str(source), destination)
        moved += 1

        per_file_caption = captions_dir / f"{source.stem}.txt"
        if per_file_caption.exists():
            per_file_caption.unlink()
            removed_captions += 1

    return RequeueExecutionResult(
        moved_count=moved,
        removed_captions=removed_captions,
        removed_workspaces=removed_workspaces,
    )
