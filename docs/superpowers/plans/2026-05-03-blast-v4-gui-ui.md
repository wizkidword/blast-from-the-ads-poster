# Blast V4 GUI/UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the desktop GUI into a tabbed, polished workstation while preserving all V3 processing behavior.

**Architecture:** Keep `social_batch_app.py` as the Tkinter shell and add small non-visual helpers for theme metadata and settings form parsing. Use the existing V3 desktop services for behavior; V4 changes layout and presentation only.

**Tech Stack:** Python 3.13, Tkinter/ttk, stdlib dataclasses/path, unittest, PyInstaller, Windows batch.

---

### Task 1: Theme Helper

**Files:**
- Create: `scripts/desktop_theme.py`
- Modify: `scripts/desktop_status.py`
- Test: `tests/test_desktop_theme.py`

- [x] Add failing tests for status card descriptors and semantic status colors.
- [x] Run `python -m unittest tests.test_desktop_theme -v` and verify it fails because `desktop_theme` does not exist.
- [x] Implement theme colors, `StatusCardSpec`, `build_status_card_specs`, `semantic_status_color`, and `apply_theme`.
- [x] Run `python -m unittest tests.test_desktop_theme -v` and verify it passes.

### Task 2: Settings Form Helper

**Files:**
- Create: `scripts/desktop_settings.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_desktop_settings.py`

- [x] Add failing tests for converting `AppSettings` to form state, parsing form state back to settings, and rejecting invalid retention values.
- [x] Run `python -m unittest tests.test_desktop_settings -v` and verify it fails because `desktop_settings` does not exist.
- [x] Implement `SettingsFormState`, `build_settings_form_state`, and `parse_settings_form_state`.
- [x] Run `python -m unittest tests.test_desktop_settings -v` and verify it passes.

### Task 3: Tabbed Desktop Layout

**Files:**
- Modify: `scripts/social_batch_app.py`

- [x] Apply the V4 theme in app startup.
- [x] Split the current stacked layout into Process, Review, Recovery, and Settings tabs.
- [x] Add status cards to the Process tab.
- [x] Move run history/recovery into the Recovery tab.
- [x] Keep the review queue and editor in the Review tab.
- [x] Keep the live log in the Process tab.

### Task 4: Settings Tab

**Files:**
- Modify: `scripts/social_batch_app.py`

- [x] Add settings form variables and controls.
- [x] Load `settings.json` into the form.
- [x] Save validated settings through `save_settings`.
- [x] Refresh review/recovery surfaces after settings save.
- [x] Never display the `.env` secret value.

### Task 5: Packaging And Docs

**Files:**
- Modify: `Build-Standalone-Exe.bat`
- Modify: `tests/test_packaging.py`
- Modify: `README.md`
- Modify: `docs/plans/v4-gui-ui-roadmap.md`

- [x] Add new V4 helper hidden imports to packaging tests and build script.
- [x] Document the V4 tabbed UI and settings tab.
- [x] Mark implemented V4 phases in the roadmap.

### Verification

- [x] Run `python -m unittest discover -s tests -v`.
- [x] Run `python -m compileall -q scripts tests`.
- [x] Run `python scripts\workflow.py setup`.
- [x] Run `python -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('scripts').resolve())); import tkinter as tk; from social_batch_app import SocialBatchApp; root=tk.Tk(); root.withdraw(); app=SocialBatchApp(root); root.update_idletasks(); root.destroy()"`.
- [x] Run `cmd /c Verify-Release.bat`.
- [x] Confirm package does not contain real `.env` files.
- [x] Confirm `inbox/` contains only `.gitkeep` and `temp/frames` is empty.

### Completion Evidence

- `tests.test_desktop_theme` and `tests.test_desktop_settings` were first run red with `ModuleNotFoundError`, then green after implementation.
- Full unit suite passed: `Ran 77 tests ... OK`.
- `python -m compileall -q scripts tests` exited `0`.
- Tk smoke test instantiated `SocialBatchApp` and confirmed tabs: `Process Review Recovery Settings`.
- `python scripts\workflow.py setup` exited `0` and reported Blast From the Ads `v4.0.0`.
- `cmd /c Verify-Release.bat` exited `0` and rebuilt the standalone EXE.
- Post-build package checks confirmed the EXE, `.env.example`, changelog, V4 README docs, no real `.env`, and V4 hidden imports.
- `inbox/` contains only `.gitkeep`; `temp/frames` has `0` files.
