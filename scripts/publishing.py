#!/usr/bin/env python3
from __future__ import annotations

import mimetypes
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under

try:
    from atomic_io import (
        InvalidSchemaError,
        atomic_write_json,
        atomic_write_text,
        load_json,
        require_json_object,
        require_known_schema_version,
    )
except ImportError:
    from scripts.atomic_io import (
        InvalidSchemaError,
        atomic_write_json,
        atomic_write_text,
        load_json,
        require_json_object,
        require_known_schema_version,
    )

try:
    from analysis_provenance import AnalysisProvenance, normalize_provenance, requires_manual_review
except ImportError:
    from scripts.analysis_provenance import AnalysisProvenance, normalize_provenance, requires_manual_review


MANIFEST_SCHEMA_VERSION = 3
_SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {1, 2, MANIFEST_SCHEMA_VERSION}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PublishStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class PublisherResult:
    ok: bool
    status: PublishStatus
    message: str
    remote_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderState:
    display_name: str
    status: str
    can_direct_publish: bool
    last_error: Optional[str]
    remote_id: Optional[str]
    updated_at: str


class Publisher(ABC):
    provider_name: str
    display_name: str
    can_direct_publish: bool = False
    supported_post_types: set[str] = {"video", "image_carousel"}

    @abstractmethod
    def validate_account(self) -> PublisherResult:
        raise NotImplementedError

    @abstractmethod
    def prepare_media(self, manifest: Dict[str, Any]) -> PublisherResult:
        raise NotImplementedError

    @abstractmethod
    def upload(self, manifest: Dict[str, Any]) -> PublisherResult:
        raise NotImplementedError

    @abstractmethod
    def publish(self, manifest: Dict[str, Any]) -> PublisherResult:
        raise NotImplementedError

    @abstractmethod
    def poll_status(self, manifest: Dict[str, Any]) -> PublisherResult:
        raise NotImplementedError

    def initial_state(self) -> ProviderState:
        validation = self.validate_account()
        return ProviderState(
            display_name=self.display_name,
            status=validation.status.value,
            can_direct_publish=self.can_direct_publish,
            last_error=None if validation.ok else validation.message,
            remote_id=validation.remote_id,
            updated_at=utc_now_iso(),
        )


class ManualExportPublisher(Publisher):
    provider_name = "manual_export"
    display_name = "Manual Export"
    can_direct_publish = False

    def validate_account(self) -> PublisherResult:
        return PublisherResult(True, PublishStatus.READY, "Local export is ready for manual posting.")

    def prepare_media(self, manifest: Dict[str, Any]) -> PublisherResult:
        return PublisherResult(True, PublishStatus.READY, "Media is already staged locally for manual posting.")

    def upload(self, manifest: Dict[str, Any]) -> PublisherResult:
        return PublisherResult(True, PublishStatus.READY, "Manual export does not upload remotely.")

    def publish(self, manifest: Dict[str, Any]) -> PublisherResult:
        return PublisherResult(False, PublishStatus.READY, "Manual export does not support direct publishing.")

    def poll_status(self, manifest: Dict[str, Any]) -> PublisherResult:
        return PublisherResult(True, PublishStatus.READY, "No remote status is tracked for manual export.")


class PublisherRegistry:
    def __init__(self) -> None:
        self._publishers: Dict[str, Publisher] = {}

    def register(self, publisher: Publisher) -> None:
        self._publishers[publisher.provider_name] = publisher

    def list_publishers(self) -> List[Publisher]:
        return [self._publishers[name] for name in sorted(self._publishers)]

    def list_provider_names(self) -> List[str]:
        return [publisher.provider_name for publisher in self.list_publishers()]

    def initial_provider_states(self) -> Dict[str, Dict[str, Any]]:
        states: Dict[str, Dict[str, Any]] = {}
        for publisher in self.list_publishers():
            states[publisher.provider_name] = asdict(publisher.initial_state())
        return states


registry = PublisherRegistry()
registry.register(ManualExportPublisher())


def list_provider_names() -> List[str]:
    return registry.list_provider_names()


def build_initial_publishing_state(default_status: PublishStatus = PublishStatus.READY) -> Dict[str, Any]:
    return {
        "workflow_status": default_status.value,
        "selected_providers": [],
        "providers": registry.initial_provider_states(),
        "platform_overrides": {},
        "history": [],
        "readiness_overrides": [],
    }


def infer_mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def normalize_hashtag_list(raw: Any) -> List[str]:
    items: List[str]
    if isinstance(raw, str):
        items = re.split(r"[\s,]+", raw)
    elif isinstance(raw, list):
        items = [str(item) for item in raw]
    else:
        items = []

    cleaned: List[str] = []
    for item in items:
        tag = str(item).strip().lower().replace("#", "").replace(" ", "")
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned


def format_hashtag_block(hashtags: List[str]) -> str:
    return " ".join(f"#{tag}" for tag in normalize_hashtag_list(hashtags))


def list_output_manifests(outputs_dir: Path) -> List[Path]:
    manifests: List[Path] = []
    if not outputs_dir.exists():
        return manifests

    for path in outputs_dir.iterdir():
        manifest_path = path / "post_manifest.json"
        if not path.is_dir() or not manifest_path.exists():
            continue
        try:
            manifests.append(resolve_existing_under(outputs_dir, manifest_path))
        except UnsafePathError:
            continue

    manifests.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return manifests


def ensure_manifest_defaults(manifest: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        raise InvalidSchemaError("Post manifest must contain a JSON object")
    manifest = dict(manifest)
    require_known_schema_version(
        manifest.get("schema_version", 1),
        document_name="Post manifest",
        supported_versions=_SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
    )
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest.setdefault("post_id", "unknown-post")
    manifest.setdefault("post_type", "video")
    manifest.setdefault("created_at", utc_now_iso())
    manifest.setdefault("updated_at", utc_now_iso())
    manifest.setdefault("source_files", [])
    manifest.setdefault("media_files", [])
    if not isinstance(manifest["source_files"], list) or not isinstance(manifest["media_files"], list):
        raise InvalidSchemaError("Post manifest source_files and media_files must be lists")
    manifest["paths"] = _mapping_section(manifest, "paths")
    manifest["analysis"] = _mapping_section(manifest, "analysis")
    manifest["content"] = _mapping_section(manifest, "content")

    analysis = manifest["analysis"]
    analysis.setdefault("source", "unknown")
    # Older manifests did not record provenance. Preserve their historic Ready
    # behavior instead of retroactively treating every existing post as a
    # manual draft; new processing always writes an explicit value.
    analysis["provenance"] = normalize_provenance(
        analysis.get("provenance") or analysis.get("source"),
        default=AnalysisProvenance.VISION,
    )
    analysis.setdefault("error", None)
    analysis.setdefault("provider", None)
    analysis.setdefault("model", None)
    analysis.setdefault("prompt_version", None)
    analysis.setdefault("cached", False)
    analysis.setdefault("input_count", None)
    analysis.setdefault("cache_key", None)
    analysis.setdefault("meta", {})
    if not isinstance(analysis["meta"], dict):
        raise InvalidSchemaError("Post manifest analysis.meta must be a JSON object")

    content = manifest["content"]
    content.setdefault("title", "")
    content.setdefault("description", "")
    content["hashtags"] = normalize_hashtag_list(content.get("hashtags", []))
    content.setdefault("caption_text", "")
    content.setdefault("details", [])

    publishing = _mapping_section(manifest, "publishing")
    manifest["publishing"] = publishing
    publishing.setdefault("workflow_status", PublishStatus.DRAFT.value)
    publishing.setdefault("selected_providers", [])
    publishing.setdefault("platform_overrides", {})
    publishing.setdefault("history", [])
    publishing.setdefault("readiness_overrides", [])
    if not isinstance(publishing["selected_providers"], list):
        raise InvalidSchemaError("Post manifest publishing.selected_providers must be a list")
    if (
        not isinstance(publishing["platform_overrides"], dict)
        or not isinstance(publishing["history"], list)
        or not isinstance(publishing["readiness_overrides"], list)
    ):
        raise InvalidSchemaError("Post manifest publishing fields have an invalid shape")

    provider_states = publishing.setdefault("providers", {})
    if not isinstance(provider_states, dict):
        raise InvalidSchemaError("Post manifest publishing.providers must be a JSON object")
    defaults = registry.initial_provider_states()
    for provider_name, state in defaults.items():
        provider_states.setdefault(provider_name, state)
        if not isinstance(provider_states[provider_name], dict):
            raise InvalidSchemaError(f"Post manifest provider state {provider_name!r} must be a JSON object")
        provider_states[provider_name].setdefault("display_name", state["display_name"])
        provider_states[provider_name].setdefault("status", state["status"])
        provider_states[provider_name].setdefault("can_direct_publish", state["can_direct_publish"])
        provider_states[provider_name].setdefault("last_error", state["last_error"])
        provider_states[provider_name].setdefault("remote_id", state["remote_id"])
        provider_states[provider_name].setdefault("updated_at", state["updated_at"])

    selected = []
    for provider_name in publishing.get("selected_providers", []):
        if provider_name in provider_states and provider_name not in selected:
            selected.append(provider_name)
    publishing["selected_providers"] = selected
    return manifest


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    manifest_path, _, _ = _manifest_roots(manifest_path, require_existing=True)
    manifest = require_json_object(load_json(manifest_path, document_name="Post manifest"), document_name="Post manifest")
    return ensure_manifest_defaults(manifest)


def build_caption_export(manifest: Dict[str, Any]) -> str:
    manifest = ensure_manifest_defaults(manifest)
    content = manifest["content"]
    hashtags = format_hashtag_block(content.get("hashtags", []))

    return f"""{content.get("title", "")}

{content.get("description", "")}

{hashtags}
"""


def save_manifest(manifest_path: Path, manifest: Dict[str, Any], *, captions_root: Path | None = None) -> None:
    manifest_path, outputs_root, project_root = _manifest_roots(manifest_path, require_existing=False)
    manifest = ensure_manifest_defaults(manifest)
    manifest["updated_at"] = utc_now_iso()
    manifest["content"]["caption_text"] = build_caption_export(manifest)

    caption_path = manifest.get("paths", {}).get("caption_path")
    resolved_caption_path: Path | None = None
    if caption_path:
        resolved_caption_path = resolve_output_under(project_root, str(caption_path))

    legacy_caption_path = manifest.get("paths", {}).get("legacy_caption_path")
    resolved_legacy_path: Path | None = None
    if legacy_caption_path:
        resolved_legacy_path = _resolve_legacy_caption_path(project_root, captions_root, str(legacy_caption_path))

    # Validate all manifest-derived destinations before changing any persisted
    # state.  An unsafe path therefore leaves the manifest and captions intact.
    manifest_path = resolve_output_under(outputs_root, manifest_path)
    atomic_write_json(manifest_path, manifest)
    if resolved_caption_path:
        resolved_caption_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_caption_path = resolve_output_under(project_root, resolved_caption_path)
        atomic_write_text(resolved_caption_path, manifest["content"]["caption_text"])
    if resolved_legacy_path:
        resolved_legacy_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_legacy_path = _resolve_legacy_caption_path(project_root, captions_root, str(legacy_caption_path))
        atomic_write_text(resolved_legacy_path, manifest["content"]["caption_text"])


def update_manifest_review(
    manifest: Dict[str, Any],
    *,
    title: str,
    description: str,
    hashtags: Any,
    selected_providers: List[str],
    workflow_status: str,
    note: str,
    readiness_reports: Sequence[Any] | None = None,
    readiness_validator: Callable[[Dict[str, Any]], Sequence[Any]] | None = None,
) -> Dict[str, Any]:
    manifest = ensure_manifest_defaults(manifest)
    original_content = dict(manifest["content"])
    manifest["content"]["title"] = title.strip()
    manifest["content"]["description"] = description.strip()
    manifest["content"]["hashtags"] = normalize_hashtag_list(hashtags)

    changed_copy = any(
        manifest["content"][field] != original_content.get(field)
        for field in ("title", "description", "hashtags")
    )
    provenance = manifest["analysis"].get("provenance")
    if requires_manual_review(provenance) and workflow_status != PublishStatus.READY.value and (changed_copy or note.strip()):
        manifest["analysis"]["provenance"] = AnalysisProvenance.EDITED_AFTER_GENERATION.value

    provider_states = manifest["publishing"]["providers"]
    cleaned_selected = [name for name in selected_providers if name in provider_states]
    if workflow_status == PublishStatus.READY.value:
        if readiness_reports is None and readiness_validator is not None:
            readiness_reports = readiness_validator(manifest)
        if readiness_reports is None:
            raise ValueError("Marking a post Ready requires a current readiness report")
        try:
            from readiness import require_ready_reports
        except ImportError:
            from scripts.readiness import require_ready_reports
        require_ready_reports(readiness_reports)
    manifest["publishing"]["selected_providers"] = cleaned_selected
    manifest["publishing"]["workflow_status"] = workflow_status
    manifest["publishing"]["history"].append(
        {
            "timestamp": utc_now_iso(),
            "action": "review_update",
            "workflow_status": workflow_status,
            "selected_providers": cleaned_selected,
            "note": note,
        }
    )
    return manifest


def record_provider_audit(
    manifest: Dict[str, Any],
    provider: str,
    action: str,
    status: str,
    message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    manifest = ensure_manifest_defaults(manifest)
    publishing = manifest["publishing"]
    provider_history = publishing.setdefault("provider_history", [])
    provider_history.append(
        {
            "timestamp": utc_now_iso(),
            "provider": provider,
            "action": action,
            "status": status,
            "message": message,
            "metadata": metadata or {},
        }
    )
    provider_state = publishing.setdefault("providers", {}).setdefault(provider, {})
    provider_state["status"] = status
    provider_state["last_error"] = None if status in {"ready", "prepared"} else message
    provider_state["updated_at"] = utc_now_iso()
    manifest["updated_at"] = utc_now_iso()
    return manifest


def _manifest_roots(manifest_path: Path, *, require_existing: bool) -> tuple[Path, Path, Path]:
    raw_path = Path(manifest_path)
    if raw_path.name != "post_manifest.json":
        raise UnsafePathError("Manifest path must name post_manifest.json")
    workspace_dir = raw_path.parent
    outputs_root = workspace_dir.parent
    project_root = outputs_root.parent
    safe_workspace = resolve_existing_under(outputs_root, workspace_dir)
    if safe_workspace.parent != outputs_root.resolve():
        raise UnsafePathError("Manifest must belong to a direct output workspace")
    safe_manifest = (
        resolve_existing_under(safe_workspace, raw_path)
        if require_existing
        else resolve_output_under(safe_workspace, raw_path.name)
    )
    return safe_manifest, outputs_root.resolve(), project_root.resolve()


def _mapping_section(manifest: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = manifest.setdefault(key, {})
    if not isinstance(value, dict):
        raise InvalidSchemaError(f"Post manifest {key} must be a JSON object")
    return dict(value)


def _resolve_legacy_caption_path(project_root: Path, captions_root: Path | None, raw_path: str) -> Path:
    """Resolve both project-relative legacy values and configured caption roots."""

    try:
        candidate = resolve_output_under(project_root, raw_path)
        if captions_root is None:
            return candidate
        resolved_captions_root = captions_root.resolve(strict=True)
        try:
            candidate.relative_to(resolved_captions_root)
        except ValueError:
            pass
        else:
            return candidate
    except UnsafePathError:
        if captions_root is None:
            raise

    if captions_root is None:
        raise UnsafePathError("Legacy caption path is outside the approved project root")
    return resolve_output_under(captions_root, raw_path)
