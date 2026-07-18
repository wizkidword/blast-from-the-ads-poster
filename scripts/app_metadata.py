#!/usr/bin/env python3
from __future__ import annotations

APP_NAME = "Blast From the Ads"
APP_VERSION = "4.1.0"
BUILD_CHANNEL = "local-windows"


def build_version_label() -> str:
    return f"{APP_NAME} v{APP_VERSION} ({BUILD_CHANNEL})"
