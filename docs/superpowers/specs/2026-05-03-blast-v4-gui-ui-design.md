# Blast V4 GUI/UI Design

## Goal

V4 upgrades the desktop app's visual organization and daily ergonomics without changing processing behavior. The app should feel like a focused workstation: Process first, Review second, Recovery nearby, Settings available, and the log still visible where daily work happens.

## Approved Direction

Use a conservative tabbed Tkinter interface. This fits the existing Windows-local app, avoids new runtime dependencies, and keeps the V3 service layer intact. The top-level areas are:

- Process: daily inbox actions, folder shortcuts, status cards, and live log.
- Review: manifest-driven queue and editor.
- Recovery: run history, failed-file retry actions, and run details.
- Settings: non-secret `settings.json` controls.

## Visual System

Add a small theme module with colors, fonts, spacing, status accents, and status-card descriptors. The palette should be quiet and operational: light background, crisp section surfaces, strong readable text, blue primary actions, red error accents, and green ready/success accents. No marketing-style hero treatment and no decorative gradients.

## Settings UI

The Settings tab edits non-secret preferences only: Gemini model, generic fallback toggle, default providers, retention days, stale draft days, and preferred platforms. `.env` remains the only place for secrets; the UI may mention whether a key is configured but must not display the key.

## Safety Constraints

The implementation must not change the media pipeline, Gemini logic, run ledger schema, recovery targeting, requeue safety rules, package secret behavior, or the `inbox/` to `!processed/` contract.

## Verification

Add tests for the non-visual theme and settings helpers. Keep all existing V3 tests passing, compile the project, run setup, run release verification, and rebuild the standalone EXE.
