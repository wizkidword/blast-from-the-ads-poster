#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import re
import shutil
from pathlib import Path
from typing import Callable, List, Optional
from uuid import uuid4

try:
    from cancellable_subprocess import run_command
except ImportError:
    from scripts.cancellable_subprocess import run_command


INSTAGRAM_VIDEO_WIDTH = 1080
INSTAGRAM_VIDEO_HEIGHT = 1920
CAROUSEL_SLIDE_SECONDS = 2.5


class MediaProcessingTimeout(RuntimeError):
    """Raised when FFmpeg work exceeds its deliberate per-operation limit."""


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
    except (FileNotFoundError, subprocess.TimeoutExpired):
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
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingTimeout(f"FFmpeg video conversion timed out after 600 seconds: {input_path.name}") from exc
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
    except subprocess.TimeoutExpired as exc:
        raise MediaProcessingTimeout(f"FFmpeg image conversion timed out after 180 seconds: {input_path.name}") from exc
    return result.returncode == 0 and output_path.exists() and get_media_dimensions(output_path) == (1080, 1350)


def create_carousel_video_from_images(
    image_paths: List[Path],
    output_path: Path,
    *,
    cancellation_check: Callable[[], None] | None = None,
) -> bool:
    if not image_paths:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = output_path.parent / ".carousel-staging" / uuid4().hex
    try:
        stage_dir.mkdir(parents=True, exist_ok=False)
        staged_images: list[Path] = []
        for index, image_path in enumerate(image_paths, start=1):
            suffix = image_path.suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                suffix = ".jpg"
            staged_path = stage_dir / f"frame-{index:06d}{suffix}"
            shutil.copy2(image_path, staged_path)
            staged_images.append(staged_path)
        concat_path = stage_dir / "frames.concat.txt"
        concat_path.write_text(_build_concat_file_text(staged_images), encoding="utf-8")
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
            "1",
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
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingTimeout(f"FFmpeg carousel generation timed out after 600 seconds") from exc
        return (
            result.returncode == 0
            and output_path.exists()
            and get_media_dimensions(output_path) == (INSTAGRAM_VIDEO_WIDTH, INSTAGRAM_VIDEO_HEIGHT)
        )
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        try:
            stage_dir.parent.rmdir()
        except OSError:
            pass


def _build_concat_file_text(image_paths: List[Path]) -> str:
    lines: List[str] = []
    for image_path in image_paths:
        lines.append(f"file '{image_path.name}'")
        lines.append(f"duration {CAROUSEL_SLIDE_SECONDS}")
    lines.append(f"file '{image_paths[-1].name}'")
    return "\n".join(lines) + "\n"
