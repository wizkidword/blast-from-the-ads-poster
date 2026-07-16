from __future__ import annotations

from dataclasses import dataclass

try:
    from settings_store import AppSettings
except ImportError:
    from scripts.settings_store import AppSettings


@dataclass(frozen=True)
class SettingsFormState:
    openai_model: str
    allow_generic_fallback_captions: bool
    default_providers: str
    logs_retention_days: str
    posting_pack_retention_days: str
    orphan_output_retention_days: str
    stale_draft_days: str
    preferred_platforms: str
    captions_dir: str
    processed_dir: str


def build_settings_form_state(settings: AppSettings) -> SettingsFormState:
    return SettingsFormState(
        openai_model=settings.openai_model,
        allow_generic_fallback_captions=settings.allow_generic_fallback_captions,
        default_providers=", ".join(settings.default_providers),
        logs_retention_days=str(settings.logs_retention_days),
        posting_pack_retention_days=str(settings.posting_pack_retention_days),
        orphan_output_retention_days=str(settings.orphan_output_retention_days),
        stale_draft_days=str(settings.stale_draft_days),
        preferred_platforms=", ".join(settings.preferred_platforms),
        captions_dir=settings.captions_dir,
        processed_dir=settings.processed_dir,
    )


def parse_settings_form_state(state: SettingsFormState) -> AppSettings:
    return AppSettings(
        openai_model=_required_text(state.openai_model, "openai_model"),
        allow_generic_fallback_captions=state.allow_generic_fallback_captions,
        default_providers=_parse_csv_tuple(state.default_providers, "default_providers"),
        logs_retention_days=_positive_int(state.logs_retention_days, "logs_retention_days"),
        posting_pack_retention_days=_positive_int(state.posting_pack_retention_days, "posting_pack_retention_days"),
        orphan_output_retention_days=_positive_int(state.orphan_output_retention_days, "orphan_output_retention_days"),
        stale_draft_days=_positive_int(state.stale_draft_days, "stale_draft_days"),
        preferred_platforms=_parse_csv_tuple(state.preferred_platforms, "preferred_platforms"),
        captions_dir=state.captions_dir.strip(),
        processed_dir=state.processed_dir.strip(),
    )


def _required_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def _parse_csv_tuple(value: str, field_name: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise ValueError(f"{field_name} must include at least one value.")
    return items


def _positive_int(value: str, field_name: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a positive whole number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive whole number.")
    return parsed
