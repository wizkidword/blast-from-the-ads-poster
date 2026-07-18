#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    max_caption_chars: int
    max_hashtags: int
    max_carousel_items: int
    allowed_extensions: tuple[str, ...]
    require_vertical: bool = False
    min_aspect_ratio: float | None = None
    max_aspect_ratio: float | None = None
    max_file_bytes: int | None = 1_000_000_000
    max_video_duration_seconds: int | None = None
    allowed_video_codecs: tuple[str, ...] = ()
    require_audio: bool = False


@dataclass(frozen=True)
class PlatformValidationResult:
    platform: str
    ok: bool
    issues: tuple[str, ...]
    warnings: tuple[str, ...]


PROFILES = {
    "manual_export": PlatformProfile("manual_export", 10000, 100, 100, (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov")),
    "instagram": PlatformProfile(
        "instagram",
        2200,
        30,
        10,
        (".jpg", ".jpeg", ".png", ".mp4"),
        require_vertical=True,
        min_aspect_ratio=0.5,
        max_aspect_ratio=0.9,
        max_video_duration_seconds=900,
        allowed_video_codecs=("h264",),
    ),
    "tiktok": PlatformProfile(
        "tiktok",
        2200,
        30,
        1,
        (".mp4", ".mov"),
        require_vertical=True,
        min_aspect_ratio=0.5,
        max_aspect_ratio=0.65,
        max_video_duration_seconds=600,
        allowed_video_codecs=("h264",),
    ),
    "facebook": PlatformProfile("facebook", 63206, 100, 80, (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov")),
}


def get_platform_profile(platform: str) -> PlatformProfile | None:
    return PROFILES.get(platform)


def validate_manifest_for_platform(manifest: dict[str, Any], platform: str) -> PlatformValidationResult:
    profile = PROFILES.get(platform)
    if profile is None:
        return PlatformValidationResult(platform=platform, ok=False, issues=(f"Unknown platform: {platform}",), warnings=())

    content = manifest.get("content", {})
    description = str(content.get("description") or content.get("caption_text") or "")
    hashtags = content.get("hashtags") or []
    media_files = _media_files_for_platform(manifest, platform)
    issues: list[str] = []
    warnings: list[str] = []

    if len(description) > profile.max_caption_chars:
        issues.append(f"Caption is {len(description)} chars; {profile.name} limit is {profile.max_caption_chars}.")
    if len(hashtags) > profile.max_hashtags:
        issues.append(f"Hashtag count is {len(hashtags)}; {profile.name} limit is {profile.max_hashtags}.")
    if manifest.get("post_type") == "image_carousel" and len(media_files) > profile.max_carousel_items:
        issues.append(f"Carousel has {len(media_files)} item(s); {profile.name} limit is {profile.max_carousel_items}.")

    for media in media_files:
        filename = str(media.get("filename") or "")
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in profile.allowed_extensions:
            issues.append(f"Media extension {suffix} is not allowed for {profile.name}: {filename}")
        width = media.get("width")
        height = media.get("height")
        if profile.require_vertical and width and height and int(height) < int(width):
            issues.append(f"Media is not vertical for {profile.name}: {filename}")
        if not width or not height:
            warnings.append(f"Missing dimensions for {filename or 'media item'}.")

    return PlatformValidationResult(platform=platform, ok=not issues, issues=tuple(issues), warnings=tuple(warnings))


def _media_files_for_platform(manifest: dict[str, Any], platform: str) -> list[dict[str, Any]]:
    media_files = [item for item in manifest.get("media_files") or [] if isinstance(item, dict)]
    if manifest.get("post_type") == "image_carousel":
        carousel_videos = [item for item in media_files if item.get("role") == "carousel_video"]
        if platform == "tiktok" and carousel_videos:
            return carousel_videos
        if platform != "tiktok":
            return [item for item in media_files if item.get("role") != "carousel_video"]
    return media_files


def media_files_for_platform(manifest: dict[str, Any], platform: str) -> list[dict[str, Any]]:
    """Return the exact ordered assets a profile would ask the user to publish."""

    return _media_files_for_platform(manifest, platform)


def format_platform_report(manifest: dict[str, Any], platforms: tuple[str, ...]) -> str:
    lines: list[str] = []
    for platform in platforms:
        result = validate_manifest_for_platform(manifest, platform)
        lines.append(f"{platform}: {'READY' if result.ok else 'CHECK'}")
        for issue in result.issues:
            lines.append(f"- ISSUE: {issue}")
        for warning in result.warnings:
            lines.append(f"- WARNING: {warning}")
    return "\n".join(lines) + ("\n" if lines else "")
