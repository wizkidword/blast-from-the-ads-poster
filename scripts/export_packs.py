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
) -> PostingPackResult:
    manifest = load_manifest(manifest_path)
    post_id = str(manifest.get("post_id") or manifest_path.parent.name)
    pack_dir = exports_dir / "posting-packs" / _safe_folder_name(post_id)
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    media_dir = pack_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    caption_text = _caption_text(manifest, manifest_path)
    caption_path = pack_dir / "caption.txt"
    caption_path.write_text(caption_text, encoding="utf-8")

    hashtags_path = pack_dir / "hashtags.txt"
    hashtags_path.write_text(format_hashtag_block(manifest.get("content", {}).get("hashtags", [])) + "\n", encoding="utf-8")

    notes_path = pack_dir / "posting-notes.txt"
    notes_path.write_text(_posting_notes(manifest), encoding="utf-8")
    _write_platform_files(pack_dir, manifest, caption_text, platforms)

    shutil.copy2(manifest_path, pack_dir / "post_manifest.json")
    media_count = 0
    for source in _media_sources(manifest, manifest_path):
        if not source.exists() or not source.is_file():
            continue
        shutil.copy2(source, media_dir / source.name)
        media_count += 1

    return PostingPackResult(
        pack_dir=pack_dir,
        media_count=media_count,
        caption_path=caption_path,
        notes_path=notes_path,
        hashtags_path=hashtags_path,
    )


def _write_platform_files(pack_dir: Path, manifest: dict[str, Any], caption_text: str, platforms: tuple[str, ...]) -> None:
    platform_dir = pack_dir / "platforms"
    platform_dir.mkdir(parents=True, exist_ok=True)
    report = format_platform_report(manifest, platforms)
    (platform_dir / "platform-validation.txt").write_text(report, encoding="utf-8")
    for platform in platforms:
        (platform_dir / f"{platform}-caption.txt").write_text(caption_text, encoding="utf-8")
        notes = format_platform_report(manifest, (platform,))
        (platform_dir / f"{platform}-notes.txt").write_text(notes, encoding="utf-8")


def _caption_text(manifest: dict[str, Any], manifest_path: Path) -> str:
    caption_path = _resolve_manifest_path(manifest_path, manifest.get("paths", {}).get("caption_path"))
    if caption_path and caption_path.exists():
        return caption_path.read_text(encoding="utf-8")
    return str(manifest.get("content", {}).get("caption_text") or manifest.get("content", {}).get("description") or "")


def _media_sources(manifest: dict[str, Any], manifest_path: Path) -> list[Path]:
    sources: list[Path] = []
    for item in manifest.get("media_files", []):
        if not isinstance(item, dict):
            continue
        resolved = _resolve_manifest_path(manifest_path, item.get("relative_path"))
        if resolved:
            sources.append(resolved)
            continue
        if item.get("filename"):
            sources.append(manifest_path.parent / "media" / str(item["filename"]))
    return sources


def _resolve_manifest_path(manifest_path: Path, raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(str(raw_path))
    if candidate.is_absolute():
        return candidate
    base_dir = manifest_path.parents[2] if len(manifest_path.parents) > 2 else manifest_path.parent
    return base_dir / candidate


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
