# Changelog

## 4.4.0 - 2026-07-18

- Added bounded AI-analysis copies, image/frame limits, proportional video sampling, duplicate-frame removal, and low-detail request defaults.
- Added local content-addressed analysis caching and strict structured-output validation with bounded, cancellable retries.
- Manifests now record provenance, model, prompt version, cache status, and provider metadata without recording secrets or media payloads.
- Added a Skip AI mode that creates editable local drafts without an API key; text-only, generic, and manual drafts require a saved review before Ready.

## 4.3.0 - 2026-07-18

- Posting packs now build in a temporary sibling folder and replace an existing pack only after every file is copied and verified.
- Each pack includes an integrity manifest with ordered media names, byte sizes, SHA-256 hashes, source-manifest provenance, and platform-profile versions.
- Failed copies, unsafe or missing media, invalid platforms, hash mismatches, and final-swap failures preserve the last valid pack.

## 4.2.0 - 2026-07-18

- Added one shared readiness report for Review, Ready transitions, and posting-pack export.
- Validates the exact rendered caption plus staged media presence, actual type/container, dimensions, size, duration, and codec against platform profiles.
- Blocks unsafe Ready transitions and records explicit readiness overrides with an audit reason.

## 4.1.0 - 2026-07-18

- Added actual-media preflight checks for file contents, image dimensions, video duration, stream metadata, and conservative resource limits.
- Added configurable non-secret media limits to `settings.json` and the Settings tab.
- Added isolated, generated FFmpeg staging names for carousel slides and extracted frames.
- Added generated-output verification before a processing transaction can commit.
- Added explicit timeout errors and tests for malformed files, extension mismatches, animated images, concurrent staging, and missing output.

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
