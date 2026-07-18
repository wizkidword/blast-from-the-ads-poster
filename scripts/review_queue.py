#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from publishing import format_hashtag_block, list_output_manifests, load_manifest, save_manifest, update_manifest_review
except ImportError:
    from scripts.publishing import format_hashtag_block, list_output_manifests, load_manifest, save_manifest, update_manifest_review

try:
    from readiness import ReadinessReport, readiness_reports_for_manifest
except ImportError:
    from scripts.readiness import ReadinessReport, readiness_reports_for_manifest


@dataclass(frozen=True)
class ReviewItem:
    manifest_path: Path
    post_id: str
    post_type: str
    status: str
    title: str
    brand: str
    year: str
    updated_at: str
    media_names: tuple[str, ...]
    description: str
    hashtags: tuple[str, ...]
    details: tuple[str, ...]
    label: str
    manifest: dict[str, Any]


def query_review_items(
    outputs_dir: Path,
    status_filter: str = "all",
    search_text: str = "",
    now_iso: str | None = None,
    stale_days: int = 30,
) -> list[ReviewItem]:
    desired_status = status_filter.strip().lower() or "all"
    query = search_text.strip().lower()
    items: list[ReviewItem] = []

    for manifest_path in list_output_manifests(outputs_dir):
        try:
            item = build_review_item(manifest_path)
        except Exception:
            continue
        if desired_status == "stale_drafts":
            if item.status != "draft" or not _is_stale(item.updated_at, now_iso, stale_days):
                continue
        elif desired_status != "all" and item.status != desired_status:
            continue
        if query and query not in _search_haystack(item):
            continue
        items.append(item)
    return items


def build_review_item(manifest_path: Path) -> ReviewItem:
    manifest = load_manifest(manifest_path)
    content = manifest.get("content", {})
    publishing = manifest.get("publishing", {})
    meta = manifest.get("analysis", {}).get("meta", {})
    media_names = tuple(
        str(item.get("filename"))
        for item in manifest.get("media_files", [])
        if item.get("filename")
    )
    title = str(content.get("title") or manifest.get("post_id") or manifest_path.parent.name)
    status = str(publishing.get("workflow_status") or "draft").lower()
    post_type = str(manifest.get("post_type") or "post")
    brand = str(meta.get("brand") or "Unknown")
    year = str(meta.get("year") or "Unknown")
    label = f"[{status.upper()}] {post_type} | {year} | {brand} | {title[:56]}"

    return ReviewItem(
        manifest_path=manifest_path,
        post_id=str(manifest.get("post_id") or manifest_path.parent.name),
        post_type=post_type,
        status=status,
        title=title,
        brand=brand,
        year=year,
        updated_at=str(manifest.get("updated_at") or "Unknown"),
        media_names=media_names,
        description=str(content.get("description") or ""),
        hashtags=tuple(str(tag) for tag in content.get("hashtags", [])),
        details=tuple(str(detail) for detail in content.get("details", []) if str(detail).strip()),
        label=label,
        manifest=manifest,
    )


def format_review_preview(item: ReviewItem) -> str:
    lines = [
        f"Title: {item.title}",
        f"Status: {item.status} | Type: {item.post_type} | Brand: {item.brand} | Year: {item.year}",
        f"Updated: {item.updated_at}",
        "",
        "Caption:",
        item.description or "(No description yet)",
        "",
        "Hashtags:",
        format_hashtag_block(list(item.hashtags)) or "(No hashtags yet)",
    ]
    if item.media_names:
        lines.extend(["", "Media:"])
        lines.extend(f"- {name}" for name in item.media_names)
    if item.details:
        lines.extend(["", "Details:"])
        lines.extend(f"- {detail}" for detail in item.details)
    return "\n".join(lines)


def bulk_update_status(
    manifest_paths: list[Path],
    workflow_status: str,
    note: str,
    *,
    captions_root: Path | None = None,
) -> int:
    pending: list[tuple[Path, dict[str, Any]]] = []
    for manifest_path in manifest_paths:
        manifest = load_manifest(manifest_path)
        content = manifest.get("content", {})
        reports = readiness_reports_for_review(manifest_path, manifest) if workflow_status == "ready" else ()
        updated = update_manifest_review(
            manifest,
            title=str(content.get("title") or manifest.get("post_id") or manifest_path.parent.name),
            description=str(content.get("description") or ""),
            hashtags=content.get("hashtags", []),
            selected_providers=manifest.get("publishing", {}).get("selected_providers", []),
            workflow_status=workflow_status,
            note=note,
            readiness_reports=reports,
        )
        pending.append((manifest_path, updated))
    for manifest_path, updated in pending:
        save_manifest(manifest_path, updated, captions_root=captions_root)
    return len(pending)


def readiness_reports_for_review(manifest_path: Path, manifest: dict[str, Any]) -> tuple[ReadinessReport, ...]:
    """Use selected destinations, with manual export as the conservative default."""

    providers = manifest.get("publishing", {}).get("selected_providers", [])
    platforms = tuple(str(provider) for provider in providers if str(provider).strip()) or ("manual_export",)
    return readiness_reports_for_manifest(manifest_path, platforms, manifest=manifest)


def _search_haystack(item: ReviewItem) -> str:
    values = [
        item.post_id,
        item.post_type,
        item.status,
        item.title,
        item.brand,
        item.year,
        item.description,
        " ".join(item.hashtags),
        " ".join(item.media_names),
    ]
    return " ".join(values).lower()


def _is_stale(updated_at: str, now_iso: str | None, stale_days: int) -> bool:
    updated = _parse_iso(updated_at)
    now = _parse_iso(now_iso or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    if not updated or not now:
        return False
    return (now - updated).days >= stale_days


def _parse_iso(value: str) -> datetime | None:
    if not value or value == "Unknown":
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
