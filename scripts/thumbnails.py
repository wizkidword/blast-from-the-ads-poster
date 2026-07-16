#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def thumbnail_path_for_media(media_path: Path, workspace_dir: Path) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", media_path.stem.lower()).strip("-") or "media"
    return workspace_dir / "thumbnails" / f"{slug}.png"


def ensure_thumbnail(media_path: Path, workspace_dir: Path) -> Path | None:
    if not media_path.exists() or shutil.which("ffmpeg") is None:
        return None
    output_path = thumbnail_path_for_media(media_path, workspace_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if media_path.suffix.lower() in IMAGE_EXTENSIONS:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(media_path),
            "-vf",
            "scale=320:-1",
            "-frames:v",
            "1",
            str(output_path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "1",
            "-i",
            str(media_path),
            "-vf",
            "scale=320:-1",
            "-frames:v",
            "1",
            str(output_path),
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return output_path if result.returncode == 0 and output_path.exists() else None
