from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional


def extract_video_frames(video_path: Path, temp_dir: Path, seconds_list: Optional[List[int]] = None) -> List[Path]:
    frame_dir = temp_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    timestamps = seconds_list or [1, 3, 5]
    frames: List[Path] = []

    for index, seconds in enumerate(timestamps, start=1):
        frame_path = frame_dir / f"{video_path.stem}_frame_{index}.jpg"
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
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


def cleanup_temp_files(paths: List[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
