from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class ReviewEditorState:
    selection_text: str
    meta_text: str
    title: str
    description: str
    hashtags_text: str
    selected_providers: List[str]
    context_text: str


def build_review_label(manifest: dict) -> str:
    publishing = manifest.get("publishing", {})
    status = str(publishing.get("workflow_status", "draft")).upper()
    title = str(manifest.get("content", {}).get("title") or manifest.get("post_id") or "Untitled post")
    post_type = str(manifest.get("post_type", "post"))
    return f"[{status}] {post_type}: {title[:70]}"


def build_review_context_text(manifest: dict, readiness_text: str = "") -> str:
    analysis = manifest.get("analysis", {})
    meta = analysis.get("meta", {})
    source_files = manifest.get("source_files", [])
    media_files = manifest.get("media_files", [])
    history = manifest.get("publishing", {}).get("history", [])

    lines = [
        f"Post ID: {manifest.get('post_id', 'Unknown')}",
        f"Type: {manifest.get('post_type', 'Unknown')}",
        f"Analysis source: {analysis.get('source', 'Unknown')}",
        f"Analysis error: {analysis.get('error') or 'None'}",
        "",
        "Analysis:",
        f"- Year: {meta.get('year', 'Unknown')}",
        f"- Decade: {meta.get('decade', 'Unknown')}",
        f"- Brand: {meta.get('brand', 'Unknown')}",
        f"- Mood: {meta.get('mood', 'Unknown')}",
        "",
        "Source files:",
    ]
    lines.extend(f"- {item.get('filename', 'Unknown')}" for item in source_files)
    lines.extend(["", "Staged media:"])
    lines.extend(f"- {item.get('filename', 'Unknown')} ({item.get('mime_type', 'unknown')})" for item in media_files)

    details = manifest.get("content", {}).get("details", [])
    if details:
        lines.extend(["", "Details:"])
        lines.extend(f"- {detail}" for detail in details)

    if history:
        lines.extend(["", "Review history:"])
        for entry in history[-6:]:
            lines.append(f"- {entry.get('timestamp', 'Unknown')} | {entry.get('workflow_status', 'unknown')} | {entry.get('note', '')}")
    if readiness_text:
        lines.extend(["", "Readiness checklist:", readiness_text])
    return "\n".join(lines)


def build_review_editor_state(
    manifest: dict,
    manifest_path: Path,
    review_preview: str = "",
    readiness_text: str = "",
) -> ReviewEditorState:
    content = manifest.get("content", {})
    publishing = manifest.get("publishing", {})
    post_id = manifest.get("post_id", manifest_path.parent.name)
    context = build_review_context_text(manifest, readiness_text=readiness_text)
    context_text = (review_preview + "\n\nContext:\n" + context).strip() if review_preview else context
    return ReviewEditorState(
        selection_text=f"Selected: {post_id}",
        meta_text=(
            f"Status: {publishing.get('workflow_status', 'draft')}    "
            f"Type: {manifest.get('post_type', 'unknown')}    "
            f"Updated: {manifest.get('updated_at', 'Unknown')}"
        ),
        title=content.get("title", ""),
        description=content.get("description", ""),
        hashtags_text=", ".join(content.get("hashtags", [])),
        selected_providers=list(publishing.get("selected_providers", [])),
        context_text=context_text,
    )
