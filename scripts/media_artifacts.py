from __future__ import annotations

import hashlib
import math
import subprocess
import shutil
from pathlib import Path
from typing import Callable, List, Optional
from uuid import uuid4

try:
    from safe_paths import resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import resolve_existing_under, resolve_output_under

try:
    from cancellable_subprocess import run_command
except ImportError:
    from scripts.cancellable_subprocess import run_command

try:
    from media_processing import MediaProcessingTimeout
except ImportError:
    from scripts.media_processing import MediaProcessingTimeout


def extract_video_frames(
    video_path: Path,
    temp_dir: Path,
    seconds_list: Optional[List[int]] = None,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> List[Path]:
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = resolve_output_under(temp_dir, Path("frames") / uuid4().hex)
    frame_dir.mkdir(parents=True, exist_ok=False)
    timestamps = seconds_list or [1, 3, 5]
    frames: List[Path] = []

    for index, seconds in enumerate(timestamps, start=1):
        if cancellation_check is not None:
            cancellation_check()
        frame_path = resolve_output_under(frame_dir, f"frame-{index:03d}.jpg")
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
            shutil.rmtree(frame_dir, ignore_errors=True)
            return []
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(frame_dir, ignore_errors=True)
            raise MediaProcessingTimeout(f"FFmpeg frame extraction timed out after 120 seconds: {video_path.name}") from exc
        if result.returncode == 0 and frame_path.exists():
            frames.append(frame_path)

    unique_frames: List[Path] = []
    seen_hashes = set()
    for frame in frames:
        try:
            key = _file_sha256(frame)
        except OSError:
            continue
        if key in seen_hashes:
            continue
        seen_hashes.add(key)
        unique_frames.append(frame)
    return unique_frames


def proportional_frame_timestamps(duration_seconds: float | None, frame_limit: int) -> List[int]:
    """Spread bounded frame samples through a video instead of taking only its start."""

    if frame_limit <= 0:
        return []
    if duration_seconds is None or duration_seconds <= 0:
        return [1, 3, 5][:frame_limit]
    count = min(frame_limit, max(1, math.ceil(duration_seconds / 30)))
    timestamps = {
        max(0, min(int(duration_seconds), round(duration_seconds * index / (count + 1))))
        for index in range(1, count + 1)
    }
    return sorted(timestamps) or [0]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_temp_files(paths: List[Path], temp_dir: Path) -> None:
    # Cleanup runs in both normal processing and a finally block.  The first
    # pass can remove the now-empty directory, so a later pass must be a safe
    # no-op instead of treating an already-cleaned workspace as unsafe.
    if not temp_dir.is_dir():
        return
    safe_temp_dir = resolve_existing_under(temp_dir, temp_dir)
    for path in paths:
        candidate = resolve_output_under(safe_temp_dir, path)
        if candidate.exists():
            resolve_existing_under(safe_temp_dir, candidate).unlink(missing_ok=True)
        parent = candidate.parent
        while parent != safe_temp_dir and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
