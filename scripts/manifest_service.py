from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from media_rules import is_video_file
except ImportError:
    from scripts.media_rules import is_video_file

try:
    from media_processing import get_media_dimensions
except ImportError:
    from scripts.media_processing import get_media_dimensions

try:
    from publishing import PublishStatus, build_initial_publishing_state, infer_mime_type, utc_now_iso
except ImportError:
    from scripts.publishing import PublishStatus, build_initial_publishing_state, infer_mime_type, utc_now_iso


def relative_to_base(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def sanitize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-") or "post"


def build_post_id(post_type: str, file_paths: List[Path]) -> str:
    slug_source = "-".join(path.stem for path in file_paths[:2]) or post_type
    slug = sanitize_slug(slug_source)[:40]
    digest = hashlib.md5("||".join(sorted(path.name for path in file_paths)).encode("utf-8")).hexdigest()[:8]
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{post_type}-{timestamp}-{slug}-{digest}"


def create_output_workspace(outputs_dir: Path, post_type: str, file_paths: List[Path]) -> Tuple[str, Path]:
    post_id = build_post_id(post_type, file_paths)
    output_dir = outputs_dir / post_id
    counter = 1
    while output_dir.exists():
        output_dir = outputs_dir / f"{post_id}-{counter}"
        counter += 1
    (output_dir / "media").mkdir(parents=True, exist_ok=False)
    return output_dir.name, output_dir


def build_media_file_record(path: Path, role: str, order: int, base_dir: Path) -> Dict:
    dimensions = get_media_dimensions(path)
    width = dimensions[0] if dimensions else None
    height = dimensions[1] if dimensions else None
    return {
        "filename": path.name,
        "relative_path": relative_to_base(path, base_dir),
        "mime_type": infer_mime_type(path),
        "role": role,
        "order": order,
        "width": width,
        "height": height,
    }


def media_role_for_post(post_type: str, path: Path) -> str:
    if post_type == "video":
        return "primary"
    if post_type == "image_carousel" and is_video_file(path):
        return "carousel_video"
    return "carousel_item"


def write_post_manifest(
    post_id: str,
    output_dir: Path,
    post_type: str,
    workflow_status: PublishStatus,
    source_files: List[Path],
    processed_files: List[Path],
    caption_text: str,
    title: str,
    description: str,
    hashtags: List[str],
    details: List[str],
    meta: Dict,
    analysis_source: str,
    analysis_error: Optional[str],
    caption_path: Path,
    legacy_caption_path: Optional[Path],
    base_dir: Path,
    inbox_dir: Path,
) -> Path:
    manifest_path = output_dir / "post_manifest.json"
    manifest = {
        "schema_version": 1,
        "post_id": post_id,
        "post_type": post_type,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "source_files": [
            {
                "filename": path.name,
                "original_relative_path": relative_to_base(inbox_dir / path.name, base_dir),
            }
            for path in source_files
        ],
        "media_files": [
            build_media_file_record(path, media_role_for_post(post_type, path), index, base_dir)
            for index, path in enumerate(processed_files, start=1)
        ],
        "paths": {
            "output_dir": relative_to_base(output_dir, base_dir),
            "manifest_path": relative_to_base(manifest_path, base_dir),
            "caption_path": relative_to_base(caption_path, base_dir),
            "legacy_caption_path": relative_to_base(legacy_caption_path, base_dir) if legacy_caption_path else None,
        },
        "analysis": {
            "source": analysis_source,
            "error": analysis_error,
            "meta": meta,
        },
        "content": {
            "title": title,
            "description": description,
            "hashtags": hashtags,
            "caption_text": caption_text,
            "details": details,
        },
        "publishing": build_initial_publishing_state(default_status=workflow_status),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def copy_processed_media_to_output(processed_path: Path, output_dir: Path, media_subdir: Path | str = "media") -> Path:
    output_media_path = output_dir / media_subdir / processed_path.name
    output_media_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(processed_path, output_media_path)
    return output_media_path
