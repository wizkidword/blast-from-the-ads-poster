# Blast From The Ads V3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the V3 roadmap as a tested production-workstation layer while preserving the daily `inbox/` to `!processed/` workflow.

**Architecture:** Add focused V3 services for settings, structured ledgers, recovery queue aggregation, platform validation, thumbnail generation, release verification, and provider audit actions. Keep `process_inbox_social.py` as the operational facade and update the GUI to expose V3 actions without replacing the existing process/review controls.

**Tech Stack:** Python 3.13, Tkinter, stdlib JSON/path/shutil/subprocess, unittest, PyInstaller, Windows batch.

---

### Task 1: Settings And App Metadata

**Files:**
- Create: `scripts/settings_store.py`
- Modify: `scripts/app_metadata.py`
- Test: `tests/test_settings_store.py`

- [x] Add failing tests for default settings, JSON round-trip, retention settings, Gemini model setting, fallback behavior setting, and provider defaults.
- [x] Implement settings load/save/validation with `.env` reserved for secrets only.
- [x] Bump version to `3.0.0`.

### Task 2: Structured Run Ledger

**Files:**
- Create: `scripts/run_ledger.py`
- Modify: `scripts/process_inbox_social.py`
- Modify: `scripts/run_history.py`
- Test: `tests/test_run_ledger.py`

- [x] Add failing tests for writing schema-versioned ledger objects and reading old JSON-array logs.
- [x] Implement ledger metadata with run id, app version, command, start/end time, dry-run/targeted flags, summary counts, and records.
- [x] Update processing to write structured ledger logs while keeping old readers compatible.

### Task 3: Smarter Recovery Queue

**Files:**
- Create: `scripts/recovery_queue.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_recovery_queue.py`

- [x] Add failing tests for aggregating failures across logs, stale/missing file detection, videos-only retry, images-only retry, and dry-run target planning.
- [x] Implement recovery queue service based on structured and legacy logs.
- [x] Add GUI recovery summary and retry mode helpers.

### Task 4: Platform-Aware Posting Packs

**Files:**
- Create: `scripts/platform_profiles.py`
- Modify: `scripts/export_packs.py`
- Test: `tests/test_platform_profiles.py`
- Test: `tests/test_export_packs.py`

- [x] Add failing tests for Instagram/TikTok/Facebook/manual profile validation.
- [x] Validate caption length, hashtag count, media extension, media dimensions, and carousel size.
- [x] Generate platform-specific notes and caption variants inside posting packs.

### Task 5: Review Queue Pro Assets And Bulk Actions

**Files:**
- Create: `scripts/thumbnails.py`
- Modify: `scripts/review_queue.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_thumbnails.py`
- Test: `tests/test_review_queue.py`

- [x] Add failing tests for thumbnail path planning and stale draft filtering.
- [x] Implement thumbnail/poster-frame generation helper with safe no-ffmpeg fallback.
- [x] Add stale draft filter data and bulk-ready/archive service helpers.

### Task 6: Publishing Provider Audit

**Files:**
- Modify: `scripts/publishing.py`
- Test: `tests/test_publishing.py`

- [x] Add failing tests for provider prepare audit entries.
- [x] Implement provider action audit history without direct remote publishing.
- [x] Keep manual export first-class and opt-in.

### Task 7: Release Discipline

**Files:**
- Create: `Verify-Release.bat`
- Modify: `Build-Standalone-Exe.bat`
- Modify: `README.md`
- Modify: `docs/plans/v3-roadmap.md`
- Test: `tests/test_packaging.py`

- [x] Add failing tests for new hidden imports and release verification script.
- [x] Implement one-command verification script.
- [x] Rebuild the EXE and confirm `.env` is not packaged.

### Verification

- [x] Run `python -m unittest discover -s tests -v`.
- [x] Run `python -m compileall -q scripts tests`.
- [x] Run `python scripts\workflow.py setup`.
- [x] Run `cmd /c Verify-Release.bat`.
- [x] Confirm `dist/.env` and `dist/BlastFromTheAds-package/.env` are absent.
- [x] Confirm `inbox/` contains only `.gitkeep` and `temp/frames` is empty.

### Completion Evidence

- `cmd /c Verify-Release.bat` exited `0` on 2026-05-03.
- Full unit suite passed: `Ran 59 tests ... OK`.
- Release script completed compile, setup, standalone build, and package secret checks.
- Post-build packaging test passed: `Ran 5 tests ... OK`.
- `scripts/process_inbox_social.py` is now a 413-line facade after extracting AI analysis, captions, manifest writing, temp media artifacts, and post orchestration.
- Package contains the EXE, `.env.example`, and `CHANGELOG.md`; real `.env` files are absent.
- `inbox/` contains only `.gitkeep`; `temp/frames` has `0` files.
