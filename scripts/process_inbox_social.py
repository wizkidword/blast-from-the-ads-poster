#!/usr/bin/env python3
"""
Social batch processor for Blast From the Ads.

- Videos are processed one-by-one
- All images in the inbox are treated as one carousel post
- Captions are generated with OpenAI when OPENAI_API_KEY is available
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from publishing import PublishStatus, build_initial_publishing_state, infer_mime_type, list_provider_names, utc_now_iso
except ImportError:
    from scripts.publishing import PublishStatus, build_initial_publishing_state, infer_mime_type, list_provider_names, utc_now_iso

try:
    from app_paths import get_project_root
except ImportError:
    from scripts.app_paths import get_project_root

try:
    from settings_store import load_settings, resolve_configured_dir
except ImportError:
    from scripts.settings_store import load_settings, resolve_configured_dir

try:
    from media_rules import (
        IMAGE_EXTENSIONS,
        SUPPORTED_EXTENSIONS,
        VIDEO_EXTENSIONS,
        is_supported_media_file,
        is_video_file,
        split_media_files,
        unique_destination,
    )
except ImportError:
    from scripts.media_rules import (
        IMAGE_EXTENSIONS,
        SUPPORTED_EXTENSIONS,
        VIDEO_EXTENSIONS,
        is_supported_media_file,
        is_video_file,
        split_media_files,
        unique_destination,
    )

try:
    from media_processing import (
        INSTAGRAM_VIDEO_HEIGHT,
        INSTAGRAM_VIDEO_WIDTH,
        create_carousel_video_from_images,
        convert_image_to_instagram,
        convert_video_to_vertical,
        get_media_dimensions,
    )
except ImportError:
    from scripts.media_processing import (
        INSTAGRAM_VIDEO_HEIGHT,
        INSTAGRAM_VIDEO_WIDTH,
        create_carousel_video_from_images,
        convert_image_to_instagram,
        convert_video_to_vertical,
        get_media_dimensions,
    )

try:
    from run_ledger import utc_now_iso, write_run_ledger
except ImportError:
    from scripts.run_ledger import utc_now_iso, write_run_ledger

try:
    from ai_analysis import (
        IMAGE_CAROUSEL_PROMPT_TEMPLATE,
        PROMPT_TEMPLATE,
        _call_openai,
        _call_openai_detailed,
        analyze_image_batch_with_fallback,
        analyze_with_fallback,
        build_filename_context,
        build_smart_title,
        call_openai,
        call_openai_with_files,
        extract_json_object,
        get_allow_generic_fallback,
        get_openai_api_key,
        get_openai_model,
        infer_carousel_meta_from_files,
        infer_meta_from_filename,
        pick_representative_files,
    )
except ImportError:
    from scripts.ai_analysis import (
        IMAGE_CAROUSEL_PROMPT_TEMPLATE,
        PROMPT_TEMPLATE,
        _call_openai,
        _call_openai_detailed,
        analyze_image_batch_with_fallback,
        analyze_with_fallback,
        build_filename_context,
        build_smart_title,
        call_openai,
        call_openai_with_files,
        extract_json_object,
        get_allow_generic_fallback,
        get_openai_api_key,
        get_openai_model,
        infer_carousel_meta_from_files,
        infer_meta_from_filename,
        pick_representative_files,
    )

try:
    from caption_builder import (
        build_caption_block,
        build_caption_payload,
        build_carousel_caption_block,
        build_carousel_caption_payload,
        normalize_hashtags,
    )
except ImportError:
    from scripts.caption_builder import (
        build_caption_block,
        build_caption_payload,
        build_carousel_caption_block,
        build_carousel_caption_payload,
        normalize_hashtags,
    )

try:
    from manifest_service import (
        build_media_file_record as _build_media_file_record,
        build_post_id,
        copy_processed_media_to_output,
        create_output_workspace as _create_output_workspace,
        relative_to_base as _relative_to_base,
        sanitize_slug,
        write_post_manifest as _write_post_manifest,
    )
except ImportError:
    from scripts.manifest_service import (
        build_media_file_record as _build_media_file_record,
        build_post_id,
        copy_processed_media_to_output,
        create_output_workspace as _create_output_workspace,
        relative_to_base as _relative_to_base,
        sanitize_slug,
        write_post_manifest as _write_post_manifest,
    )

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under

try:
    from media_artifacts import cleanup_temp_files as _cleanup_temp_files, extract_video_frames as _extract_video_frames
except ImportError:
    from scripts.media_artifacts import cleanup_temp_files as _cleanup_temp_files, extract_video_frames as _extract_video_frames

try:
    from processing_orchestrator import (
        process_image_batch as _process_image_batch,
        process_video_file as _process_video_file,
        process_video_file_with_frames as _process_video_file_with_frames,
    )
except ImportError:
    from scripts.processing_orchestrator import (
        process_image_batch as _process_image_batch,
        process_video_file as _process_video_file,
        process_video_file_with_frames as _process_video_file_with_frames,
    )

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = get_project_root()
INBOX_DIR = BASE_DIR / "inbox"
SETTINGS_PATH = BASE_DIR / "settings.json"
CAPTIONS_DIR = BASE_DIR / "captions"
PROCESSED_DIR = BASE_DIR / "!processed"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"
TEMP_DIR = BASE_DIR / "temp"


def configure_output_dirs_from_settings() -> None:
    global CAPTIONS_DIR, PROCESSED_DIR
    settings = load_settings(SETTINGS_PATH)
    CAPTIONS_DIR = resolve_configured_dir(BASE_DIR, settings.captions_dir, "captions")
    PROCESSED_DIR = resolve_configured_dir(BASE_DIR, settings.processed_dir, "!processed")


configure_output_dirs_from_settings()

# Backward-compatible exports for older local helpers that imported the old Gemini names.
get_google_api_key = get_openai_api_key
get_google_model = get_openai_model
_call_gemini = _call_openai
_call_gemini_detailed = _call_openai_detailed
call_gemini = call_openai
call_gemini_with_files = call_openai_with_files


def load_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def ensure_dirs() -> None:
    for directory in (INBOX_DIR, CAPTIONS_DIR, PROCESSED_DIR, OUTPUTS_DIR, LOGS_DIR, TEMP_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def list_inbox_files(limit: Optional[int] = None) -> List[Path]:
    files = []
    for path in sorted(INBOX_DIR.iterdir()):
        try:
            safe_path = resolve_existing_under(INBOX_DIR, path)
        except UnsafePathError:
            continue
        if is_supported_media_file(safe_path):
            files.append(safe_path)
    if limit:
        files = files[:limit]
    return files


def extract_video_frames(video_path: Path, seconds_list: Optional[List[int]] = None) -> List[Path]:
    safe_video_path = resolve_existing_under(INBOX_DIR, video_path)
    return _extract_video_frames(safe_video_path, TEMP_DIR, seconds_list=seconds_list)


def cleanup_temp_files(paths: List[Path]) -> None:
    _cleanup_temp_files(paths, TEMP_DIR)


def relative_to_base(path: Path) -> str:
    return _relative_to_base(path, BASE_DIR)


def has_failed_results(summary: List[Dict]) -> bool:
    return any(item.get("status") == "failed" for item in summary)


def create_output_workspace(post_type: str, file_paths: List[Path]) -> Tuple[str, Path]:
    return _create_output_workspace(OUTPUTS_DIR, post_type, file_paths)


def build_media_file_record(path: Path, role: str, order: int) -> Dict:
    return _build_media_file_record(path, role, order, BASE_DIR)


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
) -> Path:
    return _write_post_manifest(
        post_id=post_id,
        output_dir=output_dir,
        post_type=post_type,
        workflow_status=workflow_status,
        source_files=source_files,
        processed_files=processed_files,
        caption_text=caption_text,
        title=title,
        description=description,
        hashtags=hashtags,
        details=details,
        meta=meta,
        analysis_source=analysis_source,
        analysis_error=analysis_error,
        caption_path=caption_path,
        legacy_caption_path=legacy_caption_path,
        base_dir=OUTPUTS_DIR.parent,
        inbox_dir=INBOX_DIR,
        legacy_caption_root=CAPTIONS_DIR,
    )


def instagram_video_destination(file_path: Path, processed_dir: Path | None = None) -> Path:
    processed_dir = processed_dir or PROCESSED_DIR
    name = require_plain_filename(f"{file_path.stem}.mp4")
    return resolve_output_under(processed_dir, name)


def carousel_video_destination(post_id: str, processed_dir: Path | None = None) -> Path:
    processed_dir = processed_dir or PROCESSED_DIR
    name = require_plain_filename(f"{post_id}-carousel-video.mp4")
    return resolve_output_under(processed_dir, name)


def handle_image_conversion_and_move(
    file_path: Path,
    destination: Path,
    dry_run: bool = False,
    *,
    inbox_root: Path | None = None,
    processed_root: Path | None = None,
) -> Optional[Path]:
    if dry_run:
        print("   DRY RUN: image move and conversion skipped")
        return None

    inbox_root = inbox_root or INBOX_DIR
    processed_root = processed_root or PROCESSED_DIR
    file_path = resolve_existing_under(inbox_root, file_path)
    destination = resolve_output_under(processed_root, destination)

    dims = get_media_dimensions(file_path)
    needs_convert = True
    if dims:
        width, height = dims
        needs_convert = not (width == 1080 and height == 1350)

    if needs_convert and convert_image_to_instagram(file_path, destination):
        file_path = resolve_existing_under(inbox_root, file_path)
        file_path.unlink(missing_ok=True)
        print("   Image converted to 1080x1350")
        return destination

    file_path = resolve_existing_under(inbox_root, file_path)
    destination = resolve_output_under(processed_root, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), destination)
    print("   Image moved without conversion" if not needs_convert else "   WARNING: Image conversion failed, moved original")
    return destination


def handle_video_conversion_and_move(
    file_path: Path,
    destination: Path,
    dry_run: bool = False,
    *,
    inbox_root: Path | None = None,
    processed_root: Path | None = None,
) -> Optional[Path]:
    if dry_run:
        print("   DRY RUN: caption and file move skipped")
        return None

    inbox_root = inbox_root or INBOX_DIR
    processed_root = processed_root or PROCESSED_DIR
    file_path = resolve_existing_under(inbox_root, file_path)
    destination = resolve_output_under(processed_root, destination)

    if convert_video_to_vertical(file_path, destination):
        file_path = resolve_existing_under(inbox_root, file_path)
        file_path.unlink(missing_ok=True)
        print(f"   Video converted to {INSTAGRAM_VIDEO_WIDTH}x{INSTAGRAM_VIDEO_HEIGHT}")
        return destination

    if destination.exists():
        destination = resolve_existing_under(processed_root, destination)
        destination.unlink(missing_ok=True)
    print("   ERROR: Video conversion failed; original left in inbox")
    return None


def handle_carousel_video_creation(
    image_paths: List[Path],
    destination: Path,
    dry_run: bool = False,
    *,
    processed_root: Path | None = None,
) -> Optional[Path]:
    if dry_run:
        print("   DRY RUN: carousel video creation skipped")
        return None

    processed_root = processed_root or PROCESSED_DIR
    image_paths = [resolve_existing_under(processed_root, path) for path in image_paths]
    destination = resolve_output_under(processed_root, destination)

    if create_carousel_video_from_images(image_paths, destination):
        print("   Carousel video created for TikTok")
        return destination

    if destination.exists():
        destination = resolve_existing_under(processed_root, destination)
        destination.unlink(missing_ok=True)
    print("   ERROR: Carousel video creation failed")
    return None


def process_video_file(file_path: Path, dry_run: bool = False) -> Dict:
    return _process_video_file(file_path, sys.modules[__name__], dry_run=dry_run)


def _process_video_file_with_frames(file_path: Path, frame_paths: List[Path], dry_run: bool = False) -> Dict:
    return _process_video_file_with_frames(file_path, frame_paths, sys.modules[__name__], dry_run=dry_run)


def process_image_batch(image_files: List[Path], dry_run: bool = False) -> Optional[Dict]:
    return _process_image_batch(image_files, sys.modules[__name__], dry_run=dry_run)


def run_inbox_processing(limit: Optional[int] = None, dry_run: bool = False, target_files: Optional[List[Path]] = None) -> List[Dict]:
    started_at = utc_now_iso()
    load_env()
    ensure_dirs()
    if not get_openai_api_key():
        print("ERROR: OPENAI_API_KEY is not configured.")
        print("Create a local .env file from .env.example and add your OpenAI API key before processing.")
        print("The app now stops here so it does not generate weak fallback captions.")
        return [
            {
                "type": "run",
                "status": "failed",
                "error": "missing_openai_api_key",
                "message": "OPENAI_API_KEY is not configured.",
            }
        ]

    if target_files is not None:
        try:
            files = [resolve_existing_under(INBOX_DIR, Path(path)) for path in target_files]
        except UnsafePathError as exc:
            print(f"ERROR: Unsafe retry path refused: {exc}")
            return [
                {
                    "type": "run",
                    "status": "failed",
                    "error": "unsafe_target_path",
                    "message": str(exc),
                }
            ]
        files = [path for path in files if is_supported_media_file(path)]
        files = sorted(files)
        if limit:
            files = files[:limit]
    else:
        files = list_inbox_files(limit=limit)

    if not files:
        print("Inbox is empty. Add files to inbox/ first.")
        return []

    videos, images = split_media_files(files)

    print(f"Processing {len(files)} file(s)")
    if target_files is not None:
        print("   Mode: targeted retry")
    print(f"   Videos: {len(videos)}")
    print(f"   Images: {len(images)} (one carousel caption)")

    summary: List[Dict] = []
    try:
        for video in videos:
            try:
                summary.append(process_video_file(video, dry_run=dry_run))
            except Exception as exc:
                print(f"   ERROR: Failed to process {video.name}: {exc}")
                summary.append(
                    {
                        "type": "video",
                        "file": video.name,
                        "status": "failed",
                        "error": "unhandled_exception",
                        "message": str(exc),
                    }
                )

        if images:
            try:
                image_result = process_image_batch(images, dry_run=dry_run)
                if image_result:
                    summary.append(image_result)
            except Exception as exc:
                print(f"   ERROR: Failed to process image carousel batch: {exc}")
                summary.append(
                    {
                        "type": "image_carousel",
                        "status": "failed",
                        "error": "unhandled_exception",
                        "message": str(exc),
                        "file_count": len(images),
                        "files": [path.name for path in images],
                    }
                )
    finally:
        log_path = write_run_ledger(
            LOGS_DIR,
            records=summary,
            command="inbox",
            dry_run=dry_run,
            targeted=target_files is not None,
            started_at=started_at,
            ended_at=utc_now_iso(),
        )
        print(f"Summary saved to {log_path}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process local inbox assets into social-ready outputs")
    parser.add_argument("--limit", type=int, help="Limit number of files processed")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing or moving files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_inbox_processing(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
