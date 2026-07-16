# Blast From The Ads 3.0 Work Plan

## Version 3.0 Goal

Turn the current reliable local batch tool into a more durable production workstation for retro-ad publishing: better observability, safer recovery, platform-aware export/publishing, and cleaner internals without disrupting the daily `inbox/` to `!processed/` rhythm.

## 3.0 Implementation Status

Implemented on 2026-05-03. The V3 service layer now includes focused modules for AI analysis, caption building, manifest/workspace writing, media temp artifacts, run ledgers, recovery queues, platform validation, settings, thumbnail helpers, export packs, provider audit history, and release verification. The original `process_inbox_social.py` entry point remains as a compatibility facade and is now below the 500-line Phase 1 target.

## Phase 1: Core Architecture Cleanup

- Extract AI analysis from `process_inbox_social.py` into `ai_analysis.py`.
- Extract caption payload/block creation into `caption_builder.py`.
- Extract manifest creation/path resolution into `manifest_service.py`.
- Keep `process_inbox_social.py` as the orchestration facade so existing CLI/tests/EXE paths keep working.
- Add compatibility tests proving old imports and CLI commands still behave.

Exit criteria:
- `process_inbox_social.py` is below 500 lines.
- Existing `python scripts\workflow.py inbox` behavior is unchanged.
- All old logs and manifests still load.

## Phase 2: Structured Run Ledger

- Move from raw JSON-array run logs to a schema with `run_id`, app version, command, start/end timestamps, dry-run/targeted flags, summary counts, and records.
- Keep a reader that supports old JSON-array logs.
- Add GUI sorting/filtering for runs by status, source, date, and failure type.
- Add one-click "copy diagnostic summary" for support/debugging.

Exit criteria:
- Every new run produces a self-describing ledger file.
- GUI can inspect both old and new run logs.

## Phase 3: Smarter Recovery

- Add a recovery queue that tracks failed files across multiple runs.
- Add retry modes: retry selected file, retry all failed videos, retry failed carousel images as a new carousel, and retry with dry-run first.
- Add stale failure detection so missing files are clearly marked instead of silently skipped.

Exit criteria:
- Failed work can be retried from the GUI without manually finding files.
- Recovery actions never process unrelated inbox files.

## Phase 4: Platform-Aware Posting Packs

- Add platform profiles for Instagram, TikTok, Facebook, and manual export.
- Validate media dimensions, duration, extension, caption length, hashtag count, and carousel size per platform.
- Generate platform-specific notes and caption variants inside posting packs.
- Add "copy caption" and "open media folder" actions in the GUI.

Exit criteria:
- A posting pack can tell the user exactly what is ready and what needs adjustment per platform.

## Phase 5: Review Queue Pro

- Add thumbnail previews for images and poster frames for videos.
- Add editable per-platform caption overrides.
- Add bulk actions: mark selected ready, create packs for selected, archive selected, and filter stale drafts.
- Add keyboard-friendly review flow for daily speed.

Exit criteria:
- A user can review, edit, package, and archive batches without opening File Explorer except when intentionally exporting.

## Phase 6: Configuration And Retention

- Add `settings.json` with GUI-editable retention days, default providers, Gemini model, fallback behavior, and output preferences.
- Add a setup/settings tab with validation and safe defaults.
- Keep `.env` for secrets only.

Exit criteria:
- Non-secret behavior is editable without changing code or `.env`.
- `.env` remains private and packaging-safe.

## Phase 7: Publishing Integrations

- Start with a provider interface that can validate accounts and prepare uploads without publishing.
- Add one real direct-publish provider only after platform requirements and auth are confirmed.
- Keep manual export as a first-class provider.
- Add provider-level audit history in manifests.

Exit criteria:
- Direct publishing is opt-in and cannot replace the manual daily flow accidentally.

## Phase 8: Release Discipline

- Add changelog and app version bump process.
- Add GUI smoke tests for service helpers and non-visual state.
- Add a build verification script that runs tests, setup, compileall, package, and package-secret checks.
- Decide whether this project should become its own Git repository or remain under the larger parent tree.

Exit criteria:
- A release can be built and verified with one command.
- Changes are reviewable without noise from unrelated parent-folder files.
