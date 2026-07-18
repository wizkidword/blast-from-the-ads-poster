#!/usr/bin/env python3
from __future__ import annotations

APP_NAME = "Blast From the Ads"
APP_VERSION = "4.4.0"
BUILD_CHANNEL = "local-windows"
SUPPORTED_PYTHON_VERSION = (3, 13)

# Keep PyInstaller's dynamic-import list and the packaged smoke test in one
# importable source.  This prevents a successful build from silently omitting
# a module that the desktop app needs only after a user opens a later screen.
PACKAGE_HIDDEN_IMPORTS = (
    "ai_analysis",
    "analysis_provenance",
    "app_context",
    "app_metadata",
    "app_paths",
    "atomic_io",
    "blast_workflow",
    "cancellable_subprocess",
    "caption_builder",
    "cleanup",
    "desktop_requeue",
    "desktop_review",
    "desktop_settings",
    "desktop_status",
    "desktop_theme",
    "desktop_workflow",
    "export_packs",
    "manifest_service",
    "media_artifacts",
    "media_probe",
    "media_processing",
    "media_rules",
    "platform_profiles",
    "process_inbox_social",
    "processing_orchestrator",
    "processing_transaction",
    "publishing",
    "readiness",
    "recovery_queue",
    "recovery_service",
    "requeue",
    "review_queue",
    "run_history",
    "run_ledger",
    "safe_paths",
    "settings_store",
    "thumbnails",
    "workspace_lock",
)


def build_version_label() -> str:
    return f"{APP_NAME} v{APP_VERSION} ({BUILD_CHANNEL})"
