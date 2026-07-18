"""One shared readiness decision for review, status changes, and exports.

The report deliberately validates the rendered caption and media bytes that a
user will receive, rather than relying on a manifest's old summary fields.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

try:
    from media_probe import MediaProbeError, probe_media
except ImportError:
    from scripts.media_probe import MediaProbeError, probe_media

try:
    from platform_profiles import PlatformProfile, get_platform_profile, media_files_for_platform
except ImportError:
    from scripts.platform_profiles import PlatformProfile, get_platform_profile, media_files_for_platform

try:
    from publishing import build_caption_export, ensure_manifest_defaults, load_manifest, utc_now_iso
except ImportError:
    from scripts.publishing import build_caption_export, ensure_manifest_defaults, load_manifest, utc_now_iso

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under


class ReadinessBlockedError(ValueError):
    """Raised when a requested Ready transition has one or more blocking checks."""


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    passed: bool
    blocking: bool
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    platform: str
    checks: tuple[ReadinessCheck, ...]
    ready: bool

    @property
    def blocking_failures(self) -> tuple[ReadinessCheck, ...]:
        return tuple(check for check in self.checks if check.blocking and not check.passed)


def render_final_caption(manifest: dict[str, Any]) -> str:
    """Return the exact caption text that readiness and export both use."""

    return build_caption_export(ensure_manifest_defaults(manifest))


def readiness_report_for_manifest(
    manifest_path: Path,
    platform: str,
    *,
    manifest: dict[str, Any] | None = None,
) -> ReadinessReport:
    """Evaluate one saved workspace, or an in-memory review edit before saving it."""

    raw_path = Path(manifest_path)
    if raw_path.name != "post_manifest.json":
        raise ReadinessBlockedError("Readiness requires a post_manifest.json file")
    workspace_dir = raw_path.parent
    outputs_dir = workspace_dir.parent
    project_dir = outputs_dir.parent
    safe_manifest = resolve_existing_under(outputs_dir, raw_path)
    active_manifest = ensure_manifest_defaults(manifest) if manifest is not None else load_manifest(safe_manifest)
    return evaluate_readiness(active_manifest, platform, project_dir=project_dir, workspace_dir=safe_manifest.parent)


def readiness_reports_for_manifest(
    manifest_path: Path,
    platforms: Iterable[str],
    *,
    manifest: dict[str, Any] | None = None,
) -> tuple[ReadinessReport, ...]:
    selected = _normalized_platforms(platforms)
    return tuple(readiness_report_for_manifest(manifest_path, platform, manifest=manifest) for platform in selected)


def evaluate_readiness(
    manifest: dict[str, Any],
    platform: str,
    *,
    project_dir: Path,
    workspace_dir: Path,
) -> ReadinessReport:
    """Inspect the final caption and exact staged media for one platform profile."""

    active_manifest = ensure_manifest_defaults(manifest)
    profile = get_platform_profile(platform)
    checks: list[ReadinessCheck] = []
    if profile is None:
        checks.append(ReadinessCheck("platform_known", False, True, f"Unknown platform: {platform}"))
        return _apply_persisted_overrides(platform, checks, active_manifest)

    caption = render_final_caption(active_manifest)
    content = active_manifest["content"]
    checks.append(ReadinessCheck("caption_title", bool(str(content.get("title") or "").strip()), True, "A title is required."))
    checks.append(
        ReadinessCheck(
            "caption_description",
            bool(str(content.get("description") or "").strip()),
            True,
            "A description is required.",
        )
    )
    checks.append(
        ReadinessCheck(
            "caption_length",
            len(caption) <= profile.max_caption_chars,
            True,
            f"Final rendered caption is {len(caption)} characters; {profile.name} limit is {profile.max_caption_chars}.",
        )
    )
    hashtags = content.get("hashtags") or []
    checks.append(
        ReadinessCheck(
            "hashtag_count",
            len(hashtags) <= profile.max_hashtags,
            True,
            f"Hashtag count is {len(hashtags)}; {profile.name} limit is {profile.max_hashtags}.",
        )
    )
    _append_caption_asset_check(checks, active_manifest, project_dir)
    _append_referenced_asset_checks(checks, active_manifest, project_dir, workspace_dir)

    selected_media = media_files_for_platform(active_manifest, platform)
    checks.append(
        ReadinessCheck(
            "media_count",
            0 < len(selected_media) <= profile.max_carousel_items,
            True,
            f"{profile.name} will publish {len(selected_media)} media item(s); allowed range is 1 to {profile.max_carousel_items}.",
        )
    )
    for index, media in enumerate(selected_media, start=1):
        _append_media_checks(checks, media, index, profile, project_dir, workspace_dir)
    _append_provenance_check(checks, active_manifest)
    return _apply_persisted_overrides(profile.name, checks, active_manifest)


def record_readiness_override(
    manifest: dict[str, Any],
    report: ReadinessReport,
    codes: Iterable[str],
    reason: str,
) -> dict[str, Any]:
    """Persist an explicit, auditable override for current blocking check codes."""

    active_manifest = ensure_manifest_defaults(manifest)
    requested = tuple(dict.fromkeys(str(code).strip() for code in codes if str(code).strip()))
    clean_reason = reason.strip()
    failing_codes = {check.code for check in report.blocking_failures}
    if not requested:
        raise ReadinessBlockedError("Choose at least one blocking readiness check to override")
    if not clean_reason:
        raise ReadinessBlockedError("A reason is required for a readiness override")
    unknown = set(requested) - failing_codes
    if unknown:
        raise ReadinessBlockedError(f"Only current blocking checks can be overridden: {', '.join(sorted(unknown))}")
    entry = {"timestamp": utc_now_iso(), "platform": report.platform, "codes": list(requested), "reason": clean_reason}
    publishing = active_manifest["publishing"]
    publishing.setdefault("readiness_overrides", []).append(entry)
    publishing["history"].append(
        {
            "timestamp": entry["timestamp"],
            "action": "readiness_override",
            "workflow_status": publishing.get("workflow_status", "draft"),
            "codes": list(requested),
            "note": clean_reason,
        }
    )
    return active_manifest


def require_ready_reports(reports: Iterable[ReadinessReport]) -> None:
    blocked = [report for report in reports if not report.ready]
    if not blocked:
        return
    details = "; ".join(
        f"{report.platform}: {', '.join(check.code for check in report.blocking_failures)}" for report in blocked
    )
    raise ReadinessBlockedError(f"Cannot mark Ready while blocking checks fail ({details})")


def format_readiness_report(report: ReadinessReport) -> str:
    """Produce the same compact checklist for the Review UI and export notes."""

    lines = [f"{report.platform}: {'READY' if report.ready else 'BLOCKED'}"]
    for check in report.checks:
        if check.passed:
            state = "PASS"
        elif check.blocking:
            state = "BLOCK"
        else:
            state = "WARN"
        lines.append(f"- {state} [{check.code}] {check.message}")
    return "\n".join(lines)


def format_readiness_reports(reports: Iterable[ReadinessReport]) -> str:
    return "\n\n".join(format_readiness_report(report) for report in reports)


def _append_caption_asset_check(checks: list[ReadinessCheck], manifest: dict[str, Any], project_dir: Path) -> None:
    raw_path = manifest.get("paths", {}).get("caption_path")
    if not raw_path:
        checks.append(ReadinessCheck("caption_asset", False, True, "The workspace has no caption_path reference."))
        return
    try:
        caption_path = resolve_existing_under(project_dir, str(raw_path))
        readable = caption_path.is_file() and caption_path.stat().st_size >= 0
    except (UnsafePathError, OSError):
        readable = False
    checks.append(ReadinessCheck("caption_asset", readable, True, "The rendered caption file is readable."))


def _append_referenced_asset_checks(
    checks: list[ReadinessCheck],
    manifest: dict[str, Any],
    project_dir: Path,
    workspace_dir: Path,
) -> None:
    for index, media in enumerate(manifest.get("media_files") or [], start=1):
        if not isinstance(media, dict):
            checks.append(ReadinessCheck(f"asset_exists:{index}", False, True, "Manifest media entry is not an object."))
            continue
        path = _resolve_media_path(media, project_dir, workspace_dir)
        checks.append(
            ReadinessCheck(
                f"asset_exists:{index}",
                path is not None and path.is_file(),
                True,
                f"Referenced media asset {index} is readable." if path is not None else f"Referenced media asset {index} is missing or unsafe.",
            )
        )


def _append_media_checks(
    checks: list[ReadinessCheck],
    media: dict[str, Any],
    index: int,
    profile: PlatformProfile,
    project_dir: Path,
    workspace_dir: Path,
) -> None:
    path = _resolve_media_path(media, project_dir, workspace_dir)
    label = _media_label(media, index)
    if path is None:
        checks.append(ReadinessCheck(f"media_probe:{index}", False, True, f"Cannot inspect missing or unsafe media: {label}"))
        return
    try:
        metadata = probe_media(path)
    except MediaProbeError as exc:
        checks.append(ReadinessCheck(f"media_probe:{index}", False, True, f"Cannot inspect {label}: {exc}"))
        return
    checks.append(ReadinessCheck(f"media_probe:{index}", True, True, f"Media is readable: {label}."))
    suffix = path.suffix.lower()
    checks.append(
        ReadinessCheck(
            f"media_container:{index}",
            suffix in profile.allowed_extensions,
            True,
            f"Container {suffix or '(none)'} is allowed for {profile.name}: {label}.",
        )
    )
    type_matches_suffix = (
        metadata.actual_type == "image" and suffix in {".jpg", ".jpeg", ".png", ".webp"}
    ) or (
        metadata.actual_type == "video" and suffix in {".mp4", ".mov"}
    )
    checks.append(
        ReadinessCheck(
            f"media_type:{index}",
            type_matches_suffix,
            True,
            f"Actual media type is {metadata.actual_type}; expected file type matches {suffix or '(none)'}: {label}.",
        )
    )
    checks.append(
        ReadinessCheck(
            f"media_format:{index}",
            _format_matches_suffix(metadata.actual_type, metadata.format_name, suffix),
            True,
            f"Actual media format is {metadata.format_name}; it must match {suffix or '(none)'}: {label}.",
        )
    )
    if profile.max_file_bytes is not None:
        checks.append(
            ReadinessCheck(
                f"media_size:{index}",
                metadata.byte_size <= profile.max_file_bytes,
                True,
                f"Media is {metadata.byte_size} bytes; {profile.name} limit is {profile.max_file_bytes}.",
            )
        )
    if metadata.width is None or metadata.height is None:
        checks.append(ReadinessCheck(f"media_dimensions:{index}", False, True, f"Media dimensions are unavailable: {label}."))
    else:
        ratio = metadata.width / metadata.height
        ratio_ok = (
            (profile.min_aspect_ratio is None or ratio >= profile.min_aspect_ratio)
            and (profile.max_aspect_ratio is None or ratio <= profile.max_aspect_ratio)
        )
        vertical_ok = not profile.require_vertical or metadata.height >= metadata.width
        checks.append(
            ReadinessCheck(
                f"media_dimensions:{index}",
                ratio_ok and vertical_ok,
                True,
                f"Media dimensions are {metadata.width}x{metadata.height} (aspect {ratio:.3f}): {label}.",
            )
        )
    if metadata.actual_type == "video":
        _append_video_checks(checks, metadata, index, label, profile)


def _append_video_checks(checks: list[ReadinessCheck], metadata, index: int, label: str, profile: PlatformProfile) -> None:
    if profile.max_video_duration_seconds is not None:
        duration_ok = metadata.duration_seconds is not None and metadata.duration_seconds <= profile.max_video_duration_seconds
        value = "unknown" if metadata.duration_seconds is None else f"{metadata.duration_seconds:.1f}s"
        checks.append(
            ReadinessCheck(
                f"video_duration:{index}",
                duration_ok,
                True,
                f"Video duration is {value}; {profile.name} limit is {profile.max_video_duration_seconds}s: {label}.",
            )
        )
    if profile.allowed_video_codecs:
        checks.append(
            ReadinessCheck(
                f"video_codec:{index}",
                metadata.codec in profile.allowed_video_codecs,
                True,
                f"Video codec is {metadata.codec or 'unknown'}; allowed for {profile.name}: {', '.join(profile.allowed_video_codecs)}.",
            )
        )
    if profile.require_audio:
        checks.append(ReadinessCheck(f"video_audio:{index}", metadata.has_audio, True, f"Video audio is required for {profile.name}: {label}."))


def _append_provenance_check(checks: list[ReadinessCheck], manifest: dict[str, Any]) -> None:
    provenance = str(manifest.get("analysis", {}).get("provenance") or "").strip().lower()
    if not provenance:
        return
    needs_review = provenance in {"text_fallback", "generic_fallback"}
    checks.append(
        ReadinessCheck(
            "analysis_provenance",
            not needs_review,
            False,
            "Analysis provenance requires manual review before Ready." if needs_review else f"Analysis provenance: {provenance}.",
        )
    )


def _resolve_media_path(media: dict[str, Any], project_dir: Path, workspace_dir: Path) -> Path | None:
    raw_path = media.get("relative_path")
    try:
        if raw_path:
            return resolve_existing_under(project_dir, str(raw_path))
        filename = require_plain_filename(str(media.get("filename") or ""))
        return resolve_existing_under(workspace_dir / "media", filename)
    except (UnsafePathError, OSError):
        return None


def _media_label(media: dict[str, Any], index: int) -> str:
    return str(media.get("filename") or f"media item {index}")


def _format_matches_suffix(actual_type: str, format_name: str, suffix: str) -> bool:
    if actual_type == "image":
        expected = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}
        return expected.get(suffix) == format_name
    if actual_type == "video":
        return suffix in {".mp4", ".mov"} and bool(
            {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}.intersection(part.strip() for part in format_name.split(","))
        )
    return False


def _normalized_platforms(platforms: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for raw in platforms:
        platform = str(raw).strip()
        if platform and platform not in result:
            result.append(platform)
    return tuple(result or ("manual_export",))


def _apply_persisted_overrides(platform: str, checks: Iterable[ReadinessCheck], manifest: dict[str, Any]) -> ReadinessReport:
    active_checks = tuple(checks)
    overridden_codes = {
        str(code)
        for entry in manifest.get("publishing", {}).get("readiness_overrides", [])
        if isinstance(entry, dict) and entry.get("platform") == platform
        for code in entry.get("codes", [])
    }
    resolved = tuple(
        replace(check, passed=True, message=f"{check.message} Explicitly overridden.")
        if check.blocking and not check.passed and check.code in overridden_codes
        else check
        for check in active_checks
    )
    return ReadinessReport(platform=platform, checks=resolved, ready=not any(check.blocking and not check.passed for check in resolved))
