#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import re
from pathlib import Path
from typing import Callable, List, Optional

try:
    from cancellable_subprocess import run_command
except ImportError:
    from scripts.cancellable_subprocess import run_command


INSTAGRAM_VIDEO_WIDTH = 1080
INSTAGRAM_VIDEO_HEIGHT = 1920
CAROUSEL_SLIDE_SECONDS = 2.5


def get_media_dimensions(input_path: Path) -> Optional[tuple[int, int]]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(input_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    match = re.search(r"(?m)^\s*(\d+)\s*x\s*(\d+)", raw)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def convert_video_to_vertical(
    input_path: Path,
    output_path: Path,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> bool:
    scale_filter = (
        f"scale={INSTAGRAM_VIDEO_WIDTH}:{INSTAGRAM_VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={INSTAGRAM_VIDEO_WIDTH}:{INSTAGRAM_VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        scale_filter,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        result = run_command(cmd, timeout=600, cancellation_check=cancellation_check)
    except FileNotFoundError:
        return False
    return (
        result.returncode == 0
        and output_path.exists()
        and get_media_dimensions(output_path) == (INSTAGRAM_VIDEO_WIDTH, INSTAGRAM_VIDEO_HEIGHT)
    )


def convert_image_to_instagram(
    input_path: Path,
    output_path: Path,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> bool:
    scale_filter = (
        "scale=1080:1350:force_original_aspect_ratio=decrease,"
        "pad=1080:1350:(ow-iw)/2:(oh-ih)/2:black"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        scale_filter,
        "-q:v",
        "2",
        str(output_path),
    ]
    try:
        result = run_command(cmd, timeout=180, cancellation_check=cancellation_check)
    except FileNotFoundError:
        return False
    return result.returncode == 0 and output_path.exists()


def create_carousel_video_from_images(
    image_paths: List[Path],
    output_path: Path,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> bool:
    if not image_paths:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = output_path.with_suffix(".concat.txt")
    concat_path.write_text(_build_concat_file_text(image_paths), encoding="utf-8")
    scale_filter = (
        f"scale={INSTAGRAM_VIDEO_WIDTH}:{INSTAGRAM_VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={INSTAGRAM_VIDEO_WIDTH}:{INSTAGRAM_VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        "format=yuv420p,setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-vf",
        scale_filter,
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        result = run_command(cmd, timeout=600, cancellation_check=cancellation_check)
    except FileNotFoundError:
        return False
    finally:
        concat_path.unlink(missing_ok=True)
    return (
        result.returncode == 0
        and output_path.exists()
        and get_media_dimensions(output_path) == (INSTAGRAM_VIDEO_WIDTH, INSTAGRAM_VIDEO_HEIGHT)
    )


def _build_concat_file_text(image_paths: List[Path]) -> str:
    lines: List[str] = []
    for image_path in image_paths:
        escaped_path = str(image_path).replace("'", "'\\''")
        lines.append(f"file '{escaped_path}'")
        lines.append(f"duration {CAROUSEL_SLIDE_SECONDS}")
    escaped_last_path = str(image_paths[-1]).replace("'", "'\\''")
    lines.append(f"file '{escaped_last_path}'")
    return "\n".join(lines) + "\n"
