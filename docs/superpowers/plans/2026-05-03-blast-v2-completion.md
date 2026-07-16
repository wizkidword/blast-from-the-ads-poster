# Blast From The Ads V2 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the seven requested v2 upgrades without changing the trusted `inbox/` to `!processed/` daily workflow.

**Architecture:** Keep core processing in `process_inbox_social.py`; add focused helper modules for run history, retry/requeue targeting, export packs, cleanup retention, app metadata, and project review. Wire those helpers into the Tkinter GUI as small operational controls around the existing process/review flow.

**Tech Stack:** Python 3.13, Tkinter, stdlib JSON/path/shutil, unittest, PyInstaller.

---

### Task 1: Run Details And Recovery View

**Files:**
- Modify: `scripts/run_history.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_run_history.py`

- [ ] Add tests for detailed run records, failed candidate extraction, and formatted run detail text.
- [ ] Implement `RunRecord`, `load_inbox_run_details()`, `find_latest_run_log()`, `format_run_details()`, and `collect_failed_retry_candidates()`.
- [ ] Add GUI controls for recent-run list, latest-run detail text, open selected run log, and retry failed files from the selected run.

### Task 2: Review Queue V2

**Files:**
- Create: `scripts/review_queue.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_review_queue.py`

- [ ] Add tests for status filtering, search across title/brand/year/post id, better labels, and preview text.
- [ ] Implement manifest query helpers that load manifests safely and return display items.
- [ ] Replace direct listbox manifest loading with filtered review items and add status/search controls plus copyable preview text.

### Task 3: Targeted Retry And Resume Tools

**Files:**
- Modify: `scripts/requeue.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_requeue.py`

- [ ] Add tests for selected-workspace requeue and failed-run retry planning that ignores files already missing from `inbox/`.
- [ ] Implement selected workspace requeue plan and failed-run retry candidate helpers.
- [ ] Add GUI buttons for selected-post requeue and selected-run failed retry.

### Task 4: Export / Posting Packs

**Files:**
- Create: `scripts/export_packs.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_export_packs.py`

- [ ] Add tests proving a posting pack contains caption, media, hashtags, notes, and source manifest copy.
- [ ] Implement deterministic posting-pack creation under `exports/posting-packs/<post_id>/`.
- [ ] Add GUI button to create/open a posting pack for the selected review item.

### Task 5: Cleanup / Retention Settings

**Files:**
- Create: `scripts/cleanup.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_cleanup.py`

- [ ] Add tests for dry-run cleanup of temp frames, old logs, old exports, and orphaned output folders.
- [ ] Implement conservative retention cleanup with defaults that never touch `inbox/` or `!processed/`.
- [ ] Add GUI cleanup preview and execute flow.

### Task 6: Codebase Hardening

**Files:**
- Create: `scripts/app_metadata.py`
- Modify: `scripts/social_batch_app.py`
- Modify: `scripts/blast_workflow.py`
- Modify: `Build-Standalone-Exe.bat`
- Modify: `README.md`
- Test: `tests/test_packaging.py`

- [ ] Add version/build metadata tests and packaging hidden-import coverage for new modules.
- [ ] Implement app version/build labels and ensure setup reports version context.
- [ ] Update packaging hidden imports and README workflow docs.

### Task 7: Whole-Project Review And V3 Plan

**Files:**
- Create: `docs/reviews/2026-05-03-v2-completion-review.md`
- Create: `docs/plans/v3-roadmap.md`

- [ ] Review code structure, reliability, packaging, data durability, UX, and test coverage.
- [ ] Record remaining weak spots and improvement opportunities.
- [ ] Write a phased v3.0 roadmap with practical milestones and risk controls.

### Verification

- [ ] Run targeted tests after each task.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python -m compileall -q scripts tests`.
- [ ] Run `python scripts\workflow.py setup`.
- [ ] Rebuild with `cmd /c Build-Standalone-Exe.bat`.
- [ ] Confirm package does not include `.env`, `inbox/` is clean, and `temp/frames` stays clean.
