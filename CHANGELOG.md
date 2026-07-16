# Changelog

## 4.0.0 - 2026-05-03

- Upgraded the desktop app to a tabbed Process, Review, Recovery, and Settings layout.
- Added a V4 visual theme layer for colors, spacing, status cards, and operational state accents.
- Added Process status cards for inbox, captions, processed media, and output workspaces.
- Added a Settings tab for non-secret `settings.json` preferences.
- Added tested desktop theme and settings form helpers.
- Preserved the V3 processing, review, recovery, requeue, and packaging safety behavior.
- Bumped app metadata to `4.0.0`.

## 3.0.0 - 2026-05-03

- Added non-secret `settings.json` preferences.
- Added structured v3 run ledgers while preserving legacy log reading.
- Added recovery queue aggregation across failed runs.
- Added retry modes for all available failures, videos only, and images only.
- Added platform validation profiles for manual export, Instagram, TikTok, and Facebook.
- Added platform notes and caption variants to posting packs.
- Added thumbnail helper for review-queue media assets.
- Added stale draft filtering and bulk-ready review action.
- Added provider audit history support in manifests.
- Added `Verify-Release.bat` for release verification.
- Bumped app metadata to `3.0.0`.

## 2.0.0 - 2026-05-03

- Added run-history visibility and latest-run summaries.
- Added safer requeue behavior.
- Added posting packs, cleanup tools, and review queue improvements.
- Hardened EXE packaging so private `.env` is not copied.
