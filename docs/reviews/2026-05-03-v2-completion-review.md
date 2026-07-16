# Blast From The Ads V2 Completion Review

Date: 2026-05-03

## What Is Strong Now

- The core daily workflow is still preserved: files enter through `inbox/`, successful media lands in `!processed/`, captions land in `captions/`, and `outputs/` remains a downstream review/publishing workspace.
- Batch failures are now visible in returned summaries, CLI exit status, GUI completion messaging, and JSON run logs.
- The GUI now has a run recovery panel with recent-run details, selected-log opening, and targeted retry for failed files that remain in `inbox/`.
- The review queue is manifest-driven, filterable, searchable, and now previews caption text, hashtags, media, and extracted details before editing.
- Requeue behavior is safer: selected-post requeue prefers the primary `!processed/` file over shadow output copies, preventing duplicate regeneration.
- Posting packs provide a clean manual-export folder with caption, hashtags, notes, media, and manifest copy.
- Cleanup is conservative and retention-based. It avoids `inbox/` and `!processed/` entirely.
- Packaging no longer copies private `.env`, and tests cover hidden imports for the helper modules used by the one-file EXE.

## Remaining Weak Spots

1. `scripts/process_inbox_social.py` is still the operational hotspot at more than 1,100 lines. Media conversion has been split out, but AI analysis, caption shaping, manifest writing, and run orchestration still live together.
2. `scripts/social_batch_app.py` is now around 900 lines. The GUI is useful, but Tkinter callbacks, state management, and file operations are still coupled in one file.
3. The app still depends on direct Gemini HTTP calls from the processing thread. Retry/backoff exists, but there is no request queue, rate budget, or local cache for repeated analysis attempts.
4. Run logs are JSON arrays without a top-level schema wrapper. They work, but a richer schema with run metadata, app version, start/end time, and command context would make auditing easier.
5. Posting packs are manual-export only. They prepare assets well, but there is no platform-specific validation for Instagram/TikTok/Facebook constraints beyond current media conversion.
6. Cleanup settings are coded defaults, not user-editable or persisted in the GUI.
7. Review queue preview is text-first. It does not show image/video thumbnails yet.
8. The project folder sits inside a larger Git root where this folder currently appears untracked from the parent. That makes clean commits and change review harder unless the repo boundary is clarified.

## Inefficiencies

- Several manifest and path helpers parse similar structures independently across `publishing.py`, `review_queue.py`, `export_packs.py`, `requeue.py`, and `run_history.py`.
- GUI refreshes reload all manifests and recent logs each time. That is fine at current scale, but it will feel sluggish if `outputs/` grows into hundreds or thousands of posts.
- Image carousel analysis still loads media directly into Gemini payloads. Representative fallback helps, but there is no local image downsampling/cache step before API submission.
- The processing code uses print-driven progress. The GUI captures that output, but structured progress events would be more reliable for future UX.

## Bugs Or Risk Areas To Watch

- If a user manually edits or deletes `outputs/<post>/media` while keeping a manifest, posting-pack and selected requeue actions may have partial media. The current behavior skips missing media rather than failing loudly.
- If a targeted retry is started while unrelated files are in `inbox/`, only the selected failed paths are passed to processing, but any image retry set is still treated as a single carousel batch by design.
- `Safe Cleanup` deletes old posting-pack folders by retention age. That is intended, but it should become configurable before packs are treated as durable archives.
- `.env` loading uses simple `KEY=value` parsing. It is fine for current keys, but quoted values or comments after values are not fully dotenv-compatible.

## Improvements Made In This Pass

- Added `run_history.py` for summaries, detailed records, error formatting, and failed retry candidates.
- Added `review_queue.py` for filtered/searchable review items and preview formatting.
- Added targeted requeue/retry helpers in `requeue.py`.
- Added `export_packs.py` for manual posting packs.
- Added `cleanup.py` for retention planning and execution.
- Added `app_metadata.py` and setup/version labels.
- Split media conversion/dimension logic into `media_processing.py`.
- Added tests for run details, review filters, retry planning, posting packs, cleanup, target-file retry, metadata, and packaging hidden imports.

## Recommended Next Risk Controls

- Add a top-level run-log schema while keeping compatibility with current JSON array logs.
- Extract AI analysis into its own module with a small local cache keyed by file hash and model.
- Extract manifest path resolution into one shared helper used by review, export, requeue, and run history.
- Add a GUI smoke test strategy that can instantiate non-visual app services without requiring a display.
