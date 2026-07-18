#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

try:
    from media_probe import is_candidate_media_file as _is_candidate_media_file
except ImportError:
    from scripts.media_probe import is_candidate_media_file as _is_candidate_media_file


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_supported_media_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_candidate_media_file(path: Path) -> bool:
    """Accept supported names quickly, while allowing content-recognized media with an unexpected suffix."""

    return _is_candidate_media_file(path)


def split_media_files(file_paths: Iterable[Path]) -> Tuple[List[Path], List[Path]]:
    files = list(file_paths)
    videos = [path for path in files if is_video_file(path)]
    images = [path for path in files if is_image_file(path)]
    return videos, images


def unique_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    counter = 1
    while True:
        candidate = destination.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
