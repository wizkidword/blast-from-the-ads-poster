# Blast From the Ads

Local Windows version of the social media batch processor.

## What It Does

- Loads images and videos into `inbox/`
- Converts videos to 1080x1920 full-vertical portrait output
- Converts images to 1080x1350 portrait output
- Uses OpenAI vision models to analyze media and write titles, captions, and hashtags
- Treats all images from one run as a single carousel/gallery caption
- Creates one TikTok-ready MP4 slideshow for each image carousel while still keeping the converted images
- Writes caption exports to the configured caption export folder
- Keeps converted media in the configured processed media folder for the original posting workflow
- Creates one structured post workspace per output in `outputs/`
- Stores post manifests, ready-to-publish media, and publish-state scaffolding for v2
- Includes a desktop review queue for editing copy and marking posts draft or ready
- Shows recent run details, failures, AI source status, and recovery actions in the desktop app
- Creates posting-pack folders for manual export
- Provides conservative cleanup tools for temp frames, old logs, old posting packs, and orphan output folders
- Prevents processing, cleanup, and requeue actions from changing the same workspace at the same time
- Writes structured v3 run ledgers with app version, command context, summary counts, and records
- Tracks failed files across runs in a recovery queue
- Validates posting packs against platform profiles for manual export, Instagram, TikTok, and Facebook
- Supports non-secret `settings.json` preferences while keeping `.env` for secrets only
- Uses a V4 tabbed desktop interface with Process, Review, Recovery, and Settings work areas

## Quick Start

1. Copy `.env.example` to `.env`
2. Add your `OPENAI_API_KEY`
3. Double-click `Launch-Blast-From-The-Ads.bat`
4. Use the desktop app to add files and run a batch

## Project Folders

- `inbox/` - new files to process
- `captions/` or configured `captions_dir` - generated caption text files
- `!processed/` or configured `processed_dir` - converted videos and images ready for the original posting workflow
- `outputs/` - one folder per generated post with `post_manifest.json`, `caption.txt`, and staged media
- `logs/` - JSON run summaries
- `temp/` - temporary extracted video frames
- `exports/posting-packs/` - optional manual posting packs created from reviewed posts
- `settings.json` - optional non-secret app preferences such as retention days, OpenAI model, and default platforms

## Architecture

The daily entry point is still `scripts/process_inbox_social.py`, but it is now a small compatibility facade. The heavier responsibilities live in focused modules:

- `ai_analysis.py` - OpenAI vision prompts, retries, JSON parsing, and filename fallbacks
- `caption_builder.py` - copy blocks, hashtag normalization, and carousel captions
- `manifest_service.py` - output workspace ids, manifest writing, and media records
- `processing_orchestrator.py` - video and image-carousel processing flow
- `run_ledger.py` and `run_history.py` - structured run logs plus legacy log compatibility
- `recovery_queue.py`, `platform_profiles.py`, `settings_store.py`, and `thumbnails.py` - V3 workstation helpers
- `desktop_status.py`, `desktop_review.py`, `desktop_requeue.py`, and `desktop_workflow.py` - non-visual desktop behavior extracted from the Tkinter shell
- `desktop_theme.py` and `desktop_settings.py` - V4 visual-system metadata and settings form validation

## V4 Desktop UI

The desktop app is organized into four tabs:

- `Process` - daily inbox actions, folder shortcuts, status cards, and live log
- `Review` - manifest queue, editor, destination checks, bulk ready, and posting packs
- `Recovery` - run history, run details, and targeted failed-file retry actions
- `Settings` - non-secret preferences saved to `settings.json`

The Settings tab never displays your OpenAI API key. Keep secrets in `.env`.

## Output Workspace

Each successful post now gets its own folder in `outputs/`:

- `post_manifest.json` - structured metadata, analysis, media paths, and publish-state model
- `caption.txt` - canonical copy block for that post
- `media/` - resized video files, or image-carousel JPGs for normal carousel posting
- `tiktok/media/` - one combined MP4 slideshow for image-carousel posts

The desktop app still writes plain-text caption exports to the configured caption export folder for quick copy/paste use.

## Run Details / Recovery

The desktop app includes a run recovery panel that lets you:

- inspect the latest inbox run without opening JSON manually
- see processed/failed counts, media count, analysis source, and errors
- open the selected run log
- retry only failed files that are still present in `inbox/`
- retry all available failures, only failed videos, or only failed images from the recovery queue

## Review Queue

The desktop app now includes a review queue that lets you:

- open generated post workspaces from `outputs/`
- filter by workflow status
- search by title, brand, year, media name, or post id
- preview caption, hashtags, media, and extracted details
- edit title, description, and hashtags
- choose destination placeholders for upcoming publishers
- mark each post as `draft` or `ready`
- create a posting pack under `exports/posting-packs/`
- requeue only the selected post when you want to regenerate it
- bulk mark the currently visible filtered queue as ready
- filter stale drafts using the retention value from `settings.json`

Saving from the review queue updates both the manifest and the caption export files.

## Safe Cleanup

The `Safe Cleanup` button previews and removes only retention targets:

- stale files in `temp/frames`
- run logs older than the retention window
- posting packs older than the retention window
- orphaned `outputs/` folders that do not contain a manifest

It does not touch `inbox/` or `!processed/`.

## Platform-Aware Posting Packs

Posting packs now include a `platforms/` folder with validation notes and caption variants. The current profiles are:

- `manual_export`
- `instagram`
- `tiktok`
- `facebook`

Validation checks caption length, hashtag count, carousel size, media extensions, and vertical-media expectations where relevant.

## Settings

Create or edit `settings.json` for non-secret preferences. Secrets still belong only in `.env`.

```json
{
  "openai_model": "gpt-5.4-nano",
  "allow_generic_fallback_captions": false,
  "default_providers": ["manual_export"],
  "logs_retention_days": 90,
  "posting_pack_retention_days": 30,
  "orphan_output_retention_days": 14,
  "stale_draft_days": 30,
  "preferred_platforms": ["manual_export", "instagram", "facebook"],
  "captions_dir": "H:\\Postiz\\Captions",
  "processed_dir": "H:\\Postiz\\Processed"
}
```

Leave `captions_dir` or `processed_dir` blank to use the local `captions/` and `!processed/` folders.

## Command Line

```powershell
python scripts\workflow.py setup
python scripts\workflow.py inbox
python scripts\workflow.py inbox --dry-run
python scripts\workflow.py inbox --limit 10
python scripts\workflow.py retry
python scripts\workflow.py retry --run inbox-run-<run-id>.json --mode videos
```

## Standalone EXE

- Run `Build-Standalone-Exe.bat` to package the app as a standalone Windows executable.
- Run `Verify-Release.bat` to run tests, compile checks, setup checks, rebuild, and package-secret checks.
- The finished build lands in `dist\BlastFromTheAds.exe`
- A portable handoff folder lands in `dist\BlastFromTheAds-package\`
- The build copies `.env.example`, but it does not copy your private `.env`; add a real `.env` beside the EXE only on the machine that runs the app.

## Notes

- A processing, cleanup, or requeue action holds a workspace lock while it changes files. A second app or command will stop with the active operation details instead of touching the same media. In-progress inbox files live temporarily in `inbox/.processing/<run-id>/` and return to `inbox/` if they were not consumed.
- Each live media job is staged privately first. A completed workspace appears only after its caption, manifest, and media pass validation. Before that point, a failure returns the byte-for-byte original to `inbox/`; after that point, the original is retained in `inbox/.archive/<run-id>/` and any incomplete archival work resumes safely at the next inbox run.
- The Recovery tab, selected-run retry, and `workflow.py retry` all use the same safe retry plan. Duplicate entries are retried once, missing files are skipped, and a ledger that is malformed, unsupported, or already has a committed workspace is quarantined from automated retry while its original log remains available for inspection.
- Closing the desktop app during a run requests cancellation. It waits for the active AI or FFmpeg step to reach a safe stopping point before it closes.
- All images in `inbox/` are grouped into one carousel caption for that run.
- Videos are processed individually and each gets its own caption.
- Image carousel runs also create one vertical MP4 slideshow in `tiktok/media/` for computer-based TikTok posting.
- `ffmpeg` must be available on Windows `PATH`.
- The app now expects a real OpenAI API key.
- If OpenAI is unavailable, files stay in `inbox/` and the run logs the AI failure instead of generating weak generic captions.
- Set `ALLOW_GENERIC_FALLBACK_CAPTIONS=true` in `.env` only if you explicitly want generic emergency captions.
