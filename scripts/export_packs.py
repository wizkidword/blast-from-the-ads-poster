#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from publishing import format_hashtag_block, load_manifest
except ImportError:
    from scripts.publishing import format_hashtag_block, load_manifest

try:
    from platform_profiles import format_platform_report
except ImportError:
    from scripts.platform_profiles import format_platform_report

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under


@dataclass(frozen=True)
class PostingPackResult:
    pack_dir: Path
    media_count: int
    caption_path: Path
    notes_path: Path
    hashtags_path: Path


def create_posting_pack(
    manifest_path: Path,
    exports_dir: Path,
    platforms: tuple[str, ...] = ("manual_export", "instagram", "facebook"),
    *,
    captions_root: Path | None = None,
) -> PostingPackResult:
    manifest_path, outputs_root, project_root = _manifest_context(manifest_path)
    manifest = load_manifest(manifest_path)
    post_id = str(manifest.get("post_id") or manifest_path.parent.name)
    safe_post_id = _safe_folder_name(post_id)
    safe_platforms = tuple(require_plain_filename(platform) for platform in platforms)
    caption_text = _caption_text(manifest, manifest_path, project_root, captions_root)
    media_sources = [resolve_existing_under(project_root, source) for source in _media_sources(manifest, manifest_path, project_root)]
    if any(not source.is_file() for source in media_sources):
        raise UnsafePathError("Manifest media entry is not a regular file")

    # Complete the manifest-derived preflight before replacing an existing pack
    # or creating a new export directory.
    exports_dir.mkdir(parents=True, exist_ok=True)
    pack_dir = resolve_output_under(exports_dir, Path("posting-packs") / safe_post_id)
    if pack_dir.exists():
        shutil.rmtree(resolve_existing_under(exports_dir, pack_dir))
    media_dir = pack_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    caption_path = resolve_output_under(pack_dir, "caption.txt")
    caption_path.write_text(caption_text, encoding="utf-8")

    hashtags_path = resolve_output_under(pack_dir, "hashtags.txt")
    hashtags_path.write_text(format_hashtag_block(manifest.get("content", {}).get("hashtags", [])) + "\n", encoding="utf-8")

    notes_path = resolve_output_under(pack_dir, "posting-notes.txt")
    notes_path.write_text(_posting_notes(manifest), encoding="utf-8")
    _write_platform_files(pack_dir, manifest, caption_text, safe_platforms)

    manifest_destination = resolve_output_under(pack_dir, "post_manifest.json")
    shutil.copy2(resolve_existing_under(outputs_root, manifest_path), manifest_destination)
    media_count = 0
    for source in media_sources:
        source = resolve_existing_under(project_root, source)
        destination = resolve_output_under(media_dir, require_plain_filename(source.name))
        source = resolve_existing_under(project_root, source)
        shutil.copy2(source, destination)
        media_count += 1

    return PostingPackResult(
        pack_dir=pack_dir,
        media_count=media_count,
        caption_path=caption_path,
        notes_path=notes_path,
        hashtags_path=hashtags_path,
    )


def _write_platform_files(pack_dir: Path, manifest: dict[str, Any], caption_text: str, platforms: tuple[str, ...]) -> None:
    platform_dir = resolve_output_under(pack_dir, "platforms")
    platform_dir.mkdir(parents=True, exist_ok=True)
    report = format_platform_report(manifest, platforms)
    resolve_output_under(platform_dir, "platform-validation.txt").write_text(report, encoding="utf-8")
    for platform in platforms:
        platform_name = require_plain_filename(platform)
        resolve_output_under(platform_dir, f"{platform_name}-caption.txt").write_text(caption_text, encoding="utf-8")
        notes = format_platform_report(manifest, (platform,))
        resolve_output_under(platform_dir, f"{platform_name}-notes.txt").write_text(notes, encoding="utf-8")


def _caption_text(manifest: dict[str, Any], manifest_path: Path, project_root: Path, captions_root: Path | None) -> str:
    caption_path = _resolve_manifest_path(manifest_path, manifest.get("paths", {}).get("caption_path"), project_root)
    if caption_path and caption_path.exists():
        return resolve_existing_under(project_root, caption_path).read_text(encoding="utf-8")
    return str(manifest.get("content", {}).get("caption_text") or manifest.get("content", {}).get("description") or "")


def _media_sources(manifest: dict[str, Any], manifest_path: Path, project_root: Path) -> list[Path]:
    sources: list[Path] = []
    for item in manifest.get("media_files", []):
        if not isinstance(item, dict):
            continue
        resolved = _resolve_manifest_path(manifest_path, item.get("relative_path"), project_root)
        if resolved:
            sources.append(resolved)
            continue
        if item.get("filename"):
            sources.append(resolve_output_under(manifest_path.parent, Path("media") / require_plain_filename(str(item["filename"]))))
    return sources


def _resolve_manifest_path(manifest_path: Path, raw_path: Any, project_root: Path) -> Path | None:
    if not raw_path:
        return None
    return resolve_existing_under(project_root, str(raw_path))


def _posting_notes(manifest: dict[str, Any]) -> str:
    content = manifest.get("content", {})
    publishing = manifest.get("publishing", {})
    providers = publishing.get("selected_providers", [])
    lines = [
        f"Title: {content.get('title', '')}",
        f"Post ID: {manifest.get('post_id', '')}",
        f"Type: {manifest.get('post_type', '')}",
        f"Status: {publishing.get('workflow_status', '')}",
        f"Destinations: {', '.join(providers) if providers else 'manual_export'}",
        "",
        "Use caption.txt for the post body and media/ for upload assets.",
    ]
    return "\n".join(lines) + "\n"


def _safe_folder_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
    return cleaned.strip("-") or "post"


def _manifest_context(manifest_path: Path) -> tuple[Path, Path, Path]:
    raw_path = Path(manifest_path)
    if raw_path.name != "post_manifest.json":
        raise UnsafePathError("Posting-pack export requires a post_manifest.json file")
    outputs_root = raw_path.parent.parent
    project_root = outputs_root.parent
    safe_manifest = resolve_existing_under(outputs_root, raw_path)
    if safe_manifest.parent.parent != outputs_root.resolve():
        raise UnsafePathError("Posting-pack export requires a direct output workspace manifest")
    return safe_manifest, outputs_root.resolve(), project_root.resolve()
