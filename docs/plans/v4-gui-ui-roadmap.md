# Blast From The Ads 4.0 GUI/UI Roadmap

## Version 4.0 Goal

Upgrade the desktop experience, visual polish, scanning speed, and daily ergonomics without changing the core processing contract. V4 should be a pure GUI/UI phase: no changes to Gemini processing, media movement, run ledgers, recovery behavior, packaging secrets, or the `inbox/` to `!processed/` workflow unless a UI change reveals a bug that must be fixed.

## 4.0 Implementation Status

Implemented on 2026-05-03. The app now has a tabbed Process, Review, Recovery, and Settings layout; a small V4 theme layer; Process status cards; a non-secret Settings tab; and tests for the theme/settings helpers. The media pipeline and V3 service behavior remain unchanged.

## Non-Negotiables

- Keep `inbox/` as the daily input and `!processed/` as the primary visible processed-media destination.
- Keep `outputs/` as the review/publishing workspace, visually secondary to the daily processing flow.
- Preserve videos as individual posts and images as one carousel per run.
- Keep manual export first-class; direct publishing remains opt-in and cannot replace the daily manual flow accidentally.
- Preserve all V3 service tests before touching visual styling.

## V4 Architecture Starting Point

V3 leaves the desktop app ready for visual work:

- `scripts/social_batch_app.py` owns the Tkinter shell, layout, widgets, and user events.
- `scripts/desktop_status.py` owns folder counts and status-line formatting.
- `scripts/desktop_review.py` owns review editor display state and context text.
- `scripts/desktop_requeue.py` owns processed-output requeue execution.
- `scripts/desktop_workflow.py` owns workflow command labels, limit parsing, and action execution.

This split means V4 can redesign screens and controls while reusing stable service behavior.

## Phase 1: Information Architecture

- Separate the desktop app into clear top-level work areas: Process, Review, Recovery, Cleanup, and Settings.
- Make Process the first screen because it is the daily workflow.
- Keep Review and Recovery close enough to reach quickly, but not competing with Process.
- Replace the current long stacked layout with a tabbed or sidebar-driven layout.

Exit criteria:

- The first viewport makes the daily action obvious.
- Run/recovery/review surfaces are reachable in one click.
- Existing keyboard/mouse workflow still works.

## Phase 2: Visual System

- Define a small design token layer for fonts, spacing, borders, button widths, status colors, and text colors.
- Use consistent button groups and section headings.
- Improve contrast and hierarchy without making the app feel like a marketing page.
- Keep the operational tone: dense, clear, fast to scan.

Exit criteria:

- All controls fit on common laptop widths.
- No text overlaps or gets clipped.
- Important failure states stand out clearly.

## Phase 3: Review Queue Upgrade

- Add thumbnail/poster-frame previews beside review items.
- Make title, caption, hashtags, media details, and platform validation easier to compare.
- Add clearer ready/draft/failed/stale state badges.
- Keep bulk actions visible but harder to trigger accidentally.

Exit criteria:

- A post can be reviewed and marked ready without opening File Explorer.
- Failed/stale drafts are visually distinct from healthy drafts.

## Phase 4: Recovery And Run History UX

- Turn run history into a scan-friendly list with status, processed count, failed count, and analysis source.
- Add a clearer recovery queue panel showing available versus stale failed files.
- Add confirmation copy that names exactly what will be retried.

Exit criteria:

- A failed run can be understood and retried without opening JSON.
- Missing/stale files are explained plainly.

## Phase 5: Settings Screen

- Add GUI controls for non-secret `settings.json` preferences.
- Keep `.env` setup visible but never display the secret value.
- Validate settings before save and show what changed.

Exit criteria:

- Gemini model, fallback behavior, retention days, stale draft days, and preferred platforms are editable from the app.
- Secrets remain outside `settings.json`.

## Phase 6: V4 Verification

- Keep all existing unit tests passing.
- Add non-visual tests for any new UI-state helpers.
- Run `cmd /c Verify-Release.bat` before packaging any V4 build.
- Smoke-test the desktop app manually after packaging.

Exit criteria:

- V4 ships as an interface upgrade, not a behavior rewrite.
- The V3 daily processing guarantees remain intact.
