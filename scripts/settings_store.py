#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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


def load_settings(settings_path: Path) -> AppSettings:
    if not settings_path.exists():
        return AppSettings()
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()
    if not isinstance(raw, dict):
        return AppSettings()
    return _settings_from_dict(raw)


def save_settings(settings_path: Path, settings: AppSettings) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    payload["default_providers"] = list(settings.default_providers)
    payload["preferred_platforms"] = list(settings.preferred_platforms)
    settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _settings_from_dict(raw: dict[str, Any]) -> AppSettings:
    defaults = AppSettings()
    return AppSettings(
        openai_model=_clean_openai_model(raw, defaults.openai_model),
        allow_generic_fallback_captions=bool(raw.get("allow_generic_fallback_captions", defaults.allow_generic_fallback_captions)),
        default_providers=_clean_tuple(raw.get("default_providers"), defaults.default_providers),
        logs_retention_days=_positive_int(raw.get("logs_retention_days"), defaults.logs_retention_days),
        posting_pack_retention_days=_positive_int(raw.get("posting_pack_retention_days"), defaults.posting_pack_retention_days),
        orphan_output_retention_days=_positive_int(raw.get("orphan_output_retention_days"), defaults.orphan_output_retention_days),
        stale_draft_days=_positive_int(raw.get("stale_draft_days"), defaults.stale_draft_days),
        preferred_platforms=_clean_tuple(raw.get("preferred_platforms"), defaults.preferred_platforms),
        captions_dir=_optional_string(raw.get("captions_dir")),
        processed_dir=_optional_string(raw.get("processed_dir")),
    )


def _clean_string(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _optional_string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def resolve_configured_dir(base_dir: Path, configured_path: str, default_name: str) -> Path:
    text = _optional_string(configured_path)
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


def _clean_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    elif isinstance(value, tuple):
        items = [str(item) for item in value]
    else:
        return default
    cleaned = tuple(item.strip() for item in items if item.strip())
    return cleaned or default


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
