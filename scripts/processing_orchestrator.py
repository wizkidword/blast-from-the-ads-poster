from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from media_rules import unique_destination
except ImportError:
    from scripts.media_rules import unique_destination

try:
    from publishing import PublishStatus
except ImportError:
    from scripts.publishing import PublishStatus


def process_video_file(file_path: Path, api, dry_run: bool = False) -> Dict:
    print(f"Processing video: {file_path.name}")
    frame_paths = api.extract_video_frames(file_path)
    try:
        return process_video_file_with_frames(file_path, frame_paths, api=api, dry_run=dry_run)
    finally:
        api.cleanup_temp_files(frame_paths)


def process_video_file_with_frames(file_path: Path, frame_paths: List[Path], api, dry_run: bool = False) -> Dict:
    prompt = (
        f"{api.PROMPT_TEMPLATE}\n"
        f"Filename context: {file_path.name}\n"
        f"Normalized filename hints: {api.build_filename_context([file_path])}\n"
        "The attached frames come from the same commercial. Use them together to infer the product, era, and selling angle."
    )
    meta, analysis_source, analysis_error = api.analyze_with_fallback(
        prompt,
        frame_paths,
        api.infer_meta_from_filename(file_path),
    )

    if meta is None:
        print(f"   ERROR: AI analysis failed for {file_path.name}")
        if analysis_error:
            print(f"   {analysis_error}")
        api.cleanup_temp_files(frame_paths)
        return {
            "type": "video",
            "file": file_path.name,
            "status": "failed",
            "analysis_source": analysis_source,
            "analysis_error": analysis_error,
            "frames_used": len(frame_paths),
        }

    caption_payload = api.build_caption_payload(meta, file_path.name)
    caption_text = api.build_caption_block(meta, file_path.name)
    legacy_caption_path = api.CAPTIONS_DIR / f"{file_path.stem}.txt"

    if dry_run:
        print("   DRY RUN: manifest, caption, and file move skipped")
        caption_path = legacy_caption_path
        manifest_path = None
        output_dir = None
        processed_media_path = None
    else:
        post_id, output_dir = api.create_output_workspace("video", [file_path])
        caption_path = output_dir / "caption.txt"
        caption_path.write_text(caption_text, encoding="utf-8")
        legacy_caption_path.write_text(caption_text, encoding="utf-8")
        processed_media_path = api.handle_video_conversion_and_move(file_path, api.instagram_video_destination(file_path))
        if processed_media_path is None:
            caption_path.unlink(missing_ok=True)
            legacy_caption_path.unlink(missing_ok=True)
            shutil.rmtree(output_dir, ignore_errors=True)
            api.cleanup_temp_files(frame_paths)
            return {
                "type": "video",
                "file": file_path.name,
                "status": "failed",
                "error": "video_conversion_failed",
                "analysis_source": analysis_source,
                "analysis_error": analysis_error,
                "frames_used": len(frame_paths),
            }
        manifest_media_path = api.copy_processed_media_to_output(processed_media_path, output_dir)
        manifest_path = api.write_post_manifest(
            post_id=post_id,
            output_dir=output_dir,
            post_type="video",
            workflow_status=PublishStatus.READY,
            source_files=[file_path],
            processed_files=[manifest_media_path] if manifest_media_path else [],
            caption_text=caption_text,
            title=caption_payload["title"],
            description=caption_payload["description"],
            hashtags=caption_payload["hashtags"],
            details=caption_payload["details"],
            meta=meta,
            analysis_source=analysis_source,
            analysis_error=analysis_error,
            caption_path=caption_path,
            legacy_caption_path=legacy_caption_path,
        )

    api.cleanup_temp_files(frame_paths)
    return {
        "type": "video",
        "file": file_path.name,
        "status": "processed",
        "caption_path": str(caption_path),
        "legacy_caption_path": str(legacy_caption_path),
        "output_dir": str(output_dir) if output_dir else None,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "processed_media_path": str(processed_media_path) if processed_media_path else None,
        "brand": meta.get("brand"),
        "decade": meta.get("decade"),
        "year": meta.get("year"),
        "analysis_source": analysis_source,
        "frames_used": len(frame_paths),
        "analysis_error": analysis_error,
        "publish_status": PublishStatus.READY.value,
        "providers": api.list_provider_names(),
    }


def process_image_batch(image_files: List[Path], api, dry_run: bool = False) -> Optional[Dict]:
    if not image_files:
        return None

    print(f"Processing {len(image_files)} image(s) as one carousel batch")
    filenames_text = "\n".join(f"- {path.name}" for path in image_files)
    prompt = (
        f"{api.IMAGE_CAROUSEL_PROMPT_TEMPLATE}\n"
        f"Image filenames in this batch:\n{filenames_text}\n"
        f"Normalized filename hints: {api.build_filename_context(image_files)}\n"
        "Use logos, headlines, prices, platform names, issue branding, and recurring design motifs to make the caption smarter."
    )

    meta, analysis_source, analysis_error = api.analyze_image_batch_with_fallback(
        prompt,
        image_files,
        api.infer_carousel_meta_from_files(image_files),
    )
    if meta is None:
        print("   ERROR: AI analysis failed for image carousel batch")
        if analysis_error:
            print(f"   {analysis_error}")
        return {
            "type": "image_carousel",
            "status": "failed",
            "file_count": len(image_files),
            "files": [path.name for path in image_files],
            "analysis_source": analysis_source,
            "analysis_error": analysis_error,
        }

    caption_payload = api.build_carousel_caption_payload(meta)
    caption_text = api.build_carousel_caption_block(meta, image_files)
    legacy_caption_path = api.CAPTIONS_DIR / f"carousel-{int(time.time())}-image-batch.txt"

    if dry_run:
        print("   DRY RUN: manifest, carousel caption, and file move skipped")
        caption_path = legacy_caption_path
        manifest_path = None
        output_dir = None
        processed_files: List[Path] = []
    else:
        post_id, output_dir = api.create_output_workspace("image-carousel", image_files)
        caption_path = output_dir / "caption.txt"
        processed_files = []
        manifest_files = []
        carousel_video_path: Optional[Path] = None
        try:
            for file_path in image_files:
                print(f"Processing image: {file_path.name}")
                processed_path = api.handle_image_conversion_and_move(file_path, api.PROCESSED_DIR / file_path.name, dry_run=dry_run)
                if processed_path is None:
                    raise RuntimeError(f"Image processing did not produce an output for {file_path.name}")
                processed_files.append(processed_path)
                manifest_files.append(api.copy_processed_media_to_output(processed_path, output_dir))

            carousel_video_path = api.handle_carousel_video_creation(
                processed_files,
                api.carousel_video_destination(post_id),
                dry_run=dry_run,
            )
            if carousel_video_path is None:
                raise RuntimeError("Carousel video creation did not produce an output")
            manifest_files.append(api.copy_processed_media_to_output(carousel_video_path, output_dir, Path("tiktok") / "media"))

            caption_path.write_text(caption_text, encoding="utf-8")
            legacy_caption_path.write_text(caption_text, encoding="utf-8")
            manifest_path = api.write_post_manifest(
                post_id=post_id,
                output_dir=output_dir,
                post_type="image_carousel",
                workflow_status=PublishStatus.READY,
                source_files=image_files,
                processed_files=manifest_files,
                caption_text=caption_text,
                title=caption_payload["title"],
                description=caption_payload["description"],
                hashtags=caption_payload["hashtags"],
                details=caption_payload["details"],
                meta=meta,
                analysis_source=analysis_source,
                analysis_error=analysis_error,
                caption_path=caption_path,
                legacy_caption_path=legacy_caption_path,
            )
        except Exception as exc:
            caption_path.unlink(missing_ok=True)
            legacy_caption_path.unlink(missing_ok=True)
            if carousel_video_path and carousel_video_path.exists():
                carousel_video_path.unlink(missing_ok=True)
            for processed_path in processed_files:
                if processed_path.exists():
                    rollback_destination = unique_destination(api.INBOX_DIR / processed_path.name)
                    shutil.move(str(processed_path), rollback_destination)
            shutil.rmtree(output_dir, ignore_errors=True)
            print(f"   ERROR: Failed to finish image carousel batch: {exc}")
            return {
                "type": "image_carousel",
                "status": "failed",
                "error": "image_batch_move_failed",
                "message": str(exc),
                "file_count": len(image_files),
                "files": [path.name for path in image_files],
                "analysis_source": analysis_source,
                "analysis_error": analysis_error,
            }
    if dry_run:
        for file_path in image_files:
            print(f"Processing image: {file_path.name}")
            api.handle_image_conversion_and_move(file_path, file_path, dry_run=dry_run)
        carousel_video_path = None

    return {
        "type": "image_carousel",
        "status": "processed",
        "file_count": len(image_files),
        "files": [path.name for path in image_files],
        "caption_path": str(caption_path),
        "legacy_caption_path": str(legacy_caption_path),
        "output_dir": str(output_dir) if output_dir else None,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "processed_media_paths": [str(path) for path in processed_files] if not dry_run else [],
        "carousel_video_path": str(carousel_video_path) if carousel_video_path else None,
        "brand": meta.get("brand"),
        "decade": meta.get("decade"),
        "year": meta.get("year"),
        "analysis_source": analysis_source,
        "analysis_error": analysis_error,
        "publish_status": PublishStatus.READY.value,
        "providers": api.list_provider_names(),
    }
