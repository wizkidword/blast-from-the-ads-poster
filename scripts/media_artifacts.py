from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, List, Optional

try:
    from safe_paths import resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import resolve_existing_under, resolve_output_under

try:
    from cancellable_subprocess import run_command
except ImportError:
    from scripts.cancellable_subprocess import run_command


def extract_video_frames(
    video_path: Path,
    temp_dir: Path,
    seconds_list: Optional[List[int]] = None,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> List[Path]:
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = resolve_output_under(temp_dir, "frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    timestamps = seconds_list or [1, 3, 5]
    frames: List[Path] = []

    for index, seconds in enumerate(timestamps, start=1):
        if cancellation_check is not None:
            cancellation_check()
        frame_path = resolve_output_under(frame_dir, f"{video_path.stem}_frame_{index}.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(seconds),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ]
        try:
            result = run_command(cmd, timeout=120, cancellation_check=cancellation_check)
        except FileNotFoundError:
            return []
        if result.returncode == 0 and frame_path.exists():
            frames.append(frame_path)

    unique_frames: List[Path] = []
    seen_sizes = set()
    for frame in frames:
        try:
            key = (frame.stat().st_size, frame.name)
        except OSError:
            continue
        if key in seen_sizes:
            continue
        seen_sizes.add(key)
        unique_frames.append(frame)
    return unique_frames


def cleanup_temp_files(paths: List[Path], temp_dir: Path) -> None:
    for path in paths:
        candidate = resolve_output_under(temp_dir, path)
        if candidate.exists():
            resolve_existing_under(temp_dir, candidate).unlink(missing_ok=True)
