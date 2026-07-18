"""Stable, user-visible labels for how post copy was produced."""
from __future__ import annotations

from enum import Enum


class AnalysisProvenance(str, Enum):
    VISION = "vision"
    TEXT_FALLBACK = "text_fallback"
    GENERIC_FALLBACK = "generic_fallback"
    MANUAL = "manual"
    EDITED_AFTER_GENERATION = "edited_after_generation"


_LEGACY_PROVENANCE = {
    "openai_vision": AnalysisProvenance.VISION,
    "gemini_vision": AnalysisProvenance.VISION,
    "openai_text_only": AnalysisProvenance.TEXT_FALLBACK,
    "gemini_text_only": AnalysisProvenance.TEXT_FALLBACK,
    "fallback": AnalysisProvenance.GENERIC_FALLBACK,
}


def normalize_provenance(value: object, *, default: AnalysisProvenance = AnalysisProvenance.MANUAL) -> str:
    """Return a supported label while migrating prior source strings safely."""

    text = str(value or "").strip().lower()
    if text in {item.value for item in AnalysisProvenance}:
        return text
    if text in _LEGACY_PROVENANCE:
        return _LEGACY_PROVENANCE[text].value
    if text.startswith(("openai_vision", "gemini_vision")):
        return AnalysisProvenance.VISION.value
    return default.value


def requires_manual_review(value: object) -> bool:
    """Fallback and no-AI copy must be reviewed before a Ready transition."""

    return normalize_provenance(value) in {
        AnalysisProvenance.TEXT_FALLBACK.value,
        AnalysisProvenance.GENERIC_FALLBACK.value,
        AnalysisProvenance.MANUAL.value,
    }
