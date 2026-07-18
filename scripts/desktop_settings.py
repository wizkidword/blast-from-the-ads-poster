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
    ai_analysis_enabled: bool = True
    max_media_file_bytes: str = "1000000000"
    max_image_pixels: str = "40000000"
    max_image_dimension: str = "10000"
    max_video_duration_seconds: str = "900"
    max_carousel_images: str = "20"
    max_analysis_payload_bytes: str = "100000000"
    max_analysis_images: str = "8"
    max_analysis_image_dimension: str = "1600"
    max_analysis_request_bytes: str = "12000000"
    max_analysis_video_frames: str = "8"


def build_settings_form_state(settings: AppSettings) -> SettingsFormState:
    return SettingsFormState(
        openai_model=settings.openai_model,
        ai_analysis_enabled=settings.ai_analysis_enabled,
        allow_generic_fallback_captions=settings.allow_generic_fallback_captions,
        default_providers=", ".join(settings.default_providers),
        logs_retention_days=str(settings.logs_retention_days),
        posting_pack_retention_days=str(settings.posting_pack_retention_days),
        orphan_output_retention_days=str(settings.orphan_output_retention_days),
        stale_draft_days=str(settings.stale_draft_days),
        preferred_platforms=", ".join(settings.preferred_platforms),
        captions_dir=settings.captions_dir,
        processed_dir=settings.processed_dir,
        max_media_file_bytes=str(settings.max_media_file_bytes),
        max_image_pixels=str(settings.max_image_pixels),
        max_image_dimension=str(settings.max_image_dimension),
        max_video_duration_seconds=str(settings.max_video_duration_seconds),
        max_carousel_images=str(settings.max_carousel_images),
        max_analysis_payload_bytes=str(settings.max_analysis_payload_bytes),
        max_analysis_images=str(settings.max_analysis_images),
        max_analysis_image_dimension=str(settings.max_analysis_image_dimension),
        max_analysis_request_bytes=str(settings.max_analysis_request_bytes),
        max_analysis_video_frames=str(settings.max_analysis_video_frames),
    )


def parse_settings_form_state(state: SettingsFormState) -> AppSettings:
    return AppSettings(
        openai_model=_required_text(state.openai_model, "openai_model"),
        ai_analysis_enabled=state.ai_analysis_enabled,
        allow_generic_fallback_captions=state.allow_generic_fallback_captions,
        default_providers=_parse_csv_tuple(state.default_providers, "default_providers"),
        logs_retention_days=_positive_int(state.logs_retention_days, "logs_retention_days"),
        posting_pack_retention_days=_positive_int(state.posting_pack_retention_days, "posting_pack_retention_days"),
        orphan_output_retention_days=_positive_int(state.orphan_output_retention_days, "orphan_output_retention_days"),
        stale_draft_days=_positive_int(state.stale_draft_days, "stale_draft_days"),
        preferred_platforms=_parse_csv_tuple(state.preferred_platforms, "preferred_platforms"),
        captions_dir=state.captions_dir.strip(),
        processed_dir=state.processed_dir.strip(),
        max_media_file_bytes=_positive_int(state.max_media_file_bytes, "max_media_file_bytes"),
        max_image_pixels=_positive_int(state.max_image_pixels, "max_image_pixels"),
        max_image_dimension=_positive_int(state.max_image_dimension, "max_image_dimension"),
        max_video_duration_seconds=_positive_int(state.max_video_duration_seconds, "max_video_duration_seconds"),
        max_carousel_images=_positive_int(state.max_carousel_images, "max_carousel_images"),
        max_analysis_payload_bytes=_positive_int(state.max_analysis_payload_bytes, "max_analysis_payload_bytes"),
        max_analysis_images=_positive_int(state.max_analysis_images, "max_analysis_images"),
        max_analysis_image_dimension=_positive_int(state.max_analysis_image_dimension, "max_analysis_image_dimension"),
        max_analysis_request_bytes=_positive_int(state.max_analysis_request_bytes, "max_analysis_request_bytes"),
        max_analysis_video_frames=_positive_int(state.max_analysis_video_frames, "max_analysis_video_frames"),
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
