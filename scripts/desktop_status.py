from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StatusSnapshot:
    inbox_count: int
    caption_count: int
    processed_count: int
    output_count: int


def count_files(directory: Path, ignore_gitkeep: bool = False) -> int:
    if not directory.exists():
        return 0
    total = 0
    for path in directory.iterdir():
        if not path.is_file():
            continue
        if ignore_gitkeep and path.name == ".gitkeep":
            continue
        total += 1
    return total


def count_output_posts(outputs_dir: Path) -> int:
    if not outputs_dir.exists():
        return 0
    return sum(1 for path in outputs_dir.iterdir() if path.is_dir() and (path / "post_manifest.json").exists())


def build_status_snapshot(inbox_dir: Path, captions_dir: Path, processed_dir: Path, outputs_dir: Path) -> StatusSnapshot:
    return StatusSnapshot(
        inbox_count=count_files(inbox_dir),
        caption_count=count_files(captions_dir, ignore_gitkeep=True),
        processed_count=count_files(processed_dir, ignore_gitkeep=True),
        output_count=count_output_posts(outputs_dir),
    )


def format_status_line(snapshot: StatusSnapshot) -> str:
    return (
        f"Inbox: {snapshot.inbox_count} file(s)    "
        f"Captions: {snapshot.caption_count}    "
        f"Processed: {snapshot.processed_count}    "
        f"Outputs: {snapshot.output_count} post(s)"
    )
