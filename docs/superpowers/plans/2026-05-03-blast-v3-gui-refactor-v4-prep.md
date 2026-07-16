# Blast V3 GUI Refactor And V4 Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish V3 by extracting non-visual logic from `scripts/social_batch_app.py`, then document V4 as a pure GUI/look-and-feel upgrade phase.

**Architecture:** Keep the existing Tkinter UI and daily workflow behavior unchanged. Move status formatting, review-editor data shaping, requeue execution, and workflow action execution into focused service modules so V4 can redesign the UI without disturbing processing/review/recovery behavior.

**Tech Stack:** Python 3.13, Tkinter, stdlib dataclasses/path/shutil, unittest, PyInstaller, Windows batch.

---

### Task 1: Desktop Status Service

**Files:**
- Create: `scripts/desktop_status.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_desktop_status.py`

- [x] Write failing tests for counting folder files, ignoring `.gitkeep`, counting output posts, and formatting the status line.
- [x] Run `python -m unittest tests.test_desktop_status -v` and verify it fails because `desktop_status` does not exist.
- [x] Implement `StatusSnapshot`, `count_files`, `count_output_posts`, `build_status_snapshot`, and `format_status_line`.
- [x] Replace inline status helpers in `social_batch_app.py`.
- [x] Run `python -m unittest tests.test_desktop_status -v` and verify it passes.

### Task 2: Desktop Review Service

**Files:**
- Create: `scripts/desktop_review.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_desktop_review.py`

- [x] Write failing tests for review label building, context text generation, editor state extraction, and selected provider handling.
- [x] Run `python -m unittest tests.test_desktop_review -v` and verify it fails because `desktop_review` does not exist.
- [x] Implement `ReviewEditorState`, `build_review_label`, `build_review_context_text`, and `build_review_editor_state`.
- [x] Replace editor/context helpers in `social_batch_app.py`.
- [x] Run `python -m unittest tests.test_desktop_review -v` and verify it passes.

### Task 3: Desktop Requeue Service

**Files:**
- Create: `scripts/desktop_requeue.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_desktop_requeue.py`

- [x] Write failing tests for building the requeue confirmation summary and executing a requeue plan without duplicating shadow copies.
- [x] Run `python -m unittest tests.test_desktop_requeue -v` and verify it fails because `desktop_requeue` does not exist.
- [x] Implement `RequeueExecutionResult`, `build_requeue_confirmation`, and `execute_requeue_plan`.
- [x] Replace the long `requeue_processed_files()` body in `social_batch_app.py`.
- [x] Run `python -m unittest tests.test_desktop_requeue -v` and verify it passes.

### Task 4: Desktop Workflow Service

**Files:**
- Create: `scripts/desktop_workflow.py`
- Modify: `scripts/social_batch_app.py`
- Test: `tests/test_desktop_workflow.py`

- [x] Write failing tests for positive limit parsing, command label formatting, exit-code mapping, and unknown action failure.
- [x] Run `python -m unittest tests.test_desktop_workflow -v` and verify it fails because `desktop_workflow` does not exist.
- [x] Implement `parse_limit_value`, `format_workflow_label`, and `run_workflow_action`.
- [x] Replace inline parsing/worker branching in `social_batch_app.py`.
- [x] Run `python -m unittest tests.test_desktop_workflow -v` and verify it passes.

### Task 5: Packaging And V4 Handoff

**Files:**
- Modify: `Build-Standalone-Exe.bat`
- Modify: `tests/test_packaging.py`
- Modify: `README.md`
- Create: `docs/plans/v4-gui-ui-roadmap.md`

- [x] Add packaging tests for the new desktop service modules.
- [x] Add new hidden imports to the standalone build.
- [x] Document the V3 desktop-service architecture in `README.md`.
- [x] Write the V4 GUI/UI roadmap as a pure look-and-feel phase.

### Verification

- [x] Run `python -m unittest discover -s tests -v`.
- [x] Run `python -m compileall -q scripts tests`.
- [x] Run `python scripts\workflow.py setup`.
- [x] Run `cmd /c Verify-Release.bat`.
- [x] Confirm `dist/.env` and `dist/BlastFromTheAds-package/.env` are absent.
- [x] Confirm `inbox/` contains only `.gitkeep` and `temp/frames` is empty.

### Completion Evidence

- Each desktop service test was first run red with `ModuleNotFoundError`, then green after implementation.
- Full unit suite passed: `Ran 72 tests ... OK`.
- `python -m compileall -q scripts tests` exited `0`.
- `python scripts\workflow.py setup` exited `0` with all setup checks `[OK]`.
- `cmd /c Verify-Release.bat` exited `0` and rebuilt the standalone EXE.
- Post-build packaging tests passed: `Ran 5 tests ... OK`.
- Package contains the EXE, `.env.example`, `CHANGELOG.md`, and updated README desktop-service docs; real `.env` files are absent.
- `BlastFromTheAds.spec` includes `desktop_requeue`, `desktop_review`, `desktop_status`, and `desktop_workflow` hidden imports.
- `inbox/` contains only `.gitkeep`; `temp/frames` has `0` files.
