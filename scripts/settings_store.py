#!/usr/bin/env python3
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from atomic_io import InvalidSchemaError, atomic_write_json, load_json, require_json_object, require_known_schema_version
except ImportError:
    from scripts.atomic_io import InvalidSchemaError, atomic_write_json, load_json, require_json_object, require_known_schema_version


SETTINGS_SCHEMA_VERSION = 3
_SUPPORTED_SETTINGS_SCHEMA_VERSIONS = {1, 2, SETTINGS_SCHEMA_VERSION}


@dataclass(frozen=True)
class AppSettings:
    openai_model: str = "gpt-5.4-nano"
    allow_generic_fallback_captions: bool = False
    default_providers: tuple[str, ...] = ("manual_export",)
    logs_retention_days: int = 90
    posting_pack_retention_days: int = 30
    orphan_output_retention_days: int = 14
    stale_draft_days: int = 30
    preferred_platforms: tuple[str, ...] = ("manual_export", "instagram", "facebook")
    captions_dir: str = ""
    processed_dir: str = ""
    max_media_file_bytes: int = 1_000_000_000
    max_image_pixels: int = 40_000_000
    max_image_dimension: int = 10_000
    max_video_duration_seconds: int = 900
    max_carousel_images: int = 20
    max_analysis_payload_bytes: int = 100_000_000


def load_settings(settings_path: Path) -> AppSettings:
    if not settings_path.exists():
        return AppSettings()
    raw = require_json_object(load_json(settings_path, document_name="Settings"), document_name="Settings")
    require_known_schema_version(
        raw.get("schema_version", 1),
        document_name="Settings",
        supported_versions=_SUPPORTED_SETTINGS_SCHEMA_VERSIONS,
    )
    return _settings_from_dict(raw)


def save_settings(settings_path: Path, settings: AppSettings) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    payload["schema_version"] = SETTINGS_SCHEMA_VERSION
    payload["default_providers"] = list(settings.default_providers)
    payload["preferred_platforms"] = list(settings.preferred_platforms)
    atomic_write_json(settings_path, payload)


def _settings_from_dict(raw: dict[str, Any]) -> AppSettings:
    defaults = AppSettings()
    return AppSettings(
        openai_model=_clean_openai_model(raw, defaults.openai_model),
        allow_generic_fallback_captions=_strict_bool(raw, "allow_generic_fallback_captions", defaults.allow_generic_fallback_captions),
        default_providers=_clean_tuple(raw, "default_providers", defaults.default_providers),
        logs_retention_days=_positive_int(raw, "logs_retention_days", defaults.logs_retention_days),
        posting_pack_retention_days=_positive_int(raw, "posting_pack_retention_days", defaults.posting_pack_retention_days),
        orphan_output_retention_days=_positive_int(raw, "orphan_output_retention_days", defaults.orphan_output_retention_days),
        stale_draft_days=_positive_int(raw, "stale_draft_days", defaults.stale_draft_days),
        preferred_platforms=_clean_tuple(raw, "preferred_platforms", defaults.preferred_platforms),
        captions_dir=_optional_string(raw, "captions_dir"),
        processed_dir=_optional_string(raw, "processed_dir"),
        max_media_file_bytes=_positive_int(raw, "max_media_file_bytes", defaults.max_media_file_bytes),
        max_image_pixels=_positive_int(raw, "max_image_pixels", defaults.max_image_pixels),
        max_image_dimension=_positive_int(raw, "max_image_dimension", defaults.max_image_dimension),
        max_video_duration_seconds=_positive_int(raw, "max_video_duration_seconds", defaults.max_video_duration_seconds),
        max_carousel_images=_positive_int(raw, "max_carousel_images", defaults.max_carousel_images),
        max_analysis_payload_bytes=_positive_int(raw, "max_analysis_payload_bytes", defaults.max_analysis_payload_bytes),
    )


def _clean_string(value: Any, default: str) -> str:
    if value is not None and not isinstance(value, str):
        raise InvalidSchemaError("Settings values must be strings")
    text = str(value).strip() if value is not None else ""
    return text or default


def _optional_string(raw: dict[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InvalidSchemaError(f"Settings {field_name} must be a string")
    return value.strip()


def resolve_configured_dir(base_dir: Path, configured_path: str, default_name: str) -> Path:
    if not isinstance(configured_path, str):
        raise InvalidSchemaError("Configured directory paths must be strings")
    text = configured_path.strip()
    if not text:
        return base_dir / default_name
    expanded = Path(os.path.expandvars(os.path.expanduser(text)))
    if expanded.is_absolute():
        return expanded
    return base_dir / expanded


def _clean_openai_model(raw: dict[str, Any], default: str) -> str:
    if "openai_model" in raw:
        return _clean_string(raw.get("openai_model"), default)

    legacy_model = _clean_string(raw.get("gemini_model"), "")
    if legacy_model.lower().startswith("gpt"):
        return legacy_model

    return default


def _clean_tuple(raw: dict[str, Any], field_name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if field_name not in raw:
        return default
    value = raw[field_name]
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise InvalidSchemaError(f"Settings {field_name} must be a list of strings")
    items = list(value)
    cleaned = tuple(item.strip() for item in items if item.strip())
    return cleaned or default


def _positive_int(raw: dict[str, Any], field_name: str, default: int) -> int:
    if field_name not in raw:
        return default
    value = raw[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidSchemaError(f"Settings {field_name} must be a positive integer")
    return value


def _strict_bool(raw: dict[str, Any], field_name: str, default: bool) -> bool:
    if field_name not in raw:
        return default
    value = raw[field_name]
    if not isinstance(value, bool):
        raise InvalidSchemaError(f"Settings {field_name} must be true or false, not {value!r}")
    return value
