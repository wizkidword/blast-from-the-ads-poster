# Development

## Supported environment

- Windows 10/11
- Python 3.13
- FFmpeg and FFprobe on `PATH` for live media processing

## Setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add `OPENAI_API_KEY` to the local `.env` file only when running real media
analysis. The test suite does not need an API key or real input media.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts\workflow.py setup
```

The GitHub Actions workflow runs the first command on Windows with Python 3.13.

## Workstation paths

The tracked `settings.json` preserves the current workstation's caption and
processed-media locations. Before running the live setup check on another
machine, update those two values in the Settings tab (or leave them blank for
the local `captions/` and `!processed/` folders). The configured drive must be
mounted and writable. Each operation builds one validated directory context
from `settings.json`; it rejects missing, file-valued, overlapping, nested, or
non-writable managed folders before it moves or creates media.

Saving settings validates the selected folders before writing the new values.
The desktop app uses the resulting context immediately, so no restart is
needed for processing, status, review, recovery, or export to use the new
caption and processed-media locations.

## Local document safety

Settings, run ledgers, and post manifests are written atomically: the app saves
a complete sibling temporary file, then replaces the old file only after the
new one is ready. Existing legacy documents are migrated in memory when read.
If the app reports that one of these JSON documents is corrupt or uses an
unknown schema version, stop before requeueing or editing it and restore or
repair that specific file from a known-good copy. The app will not silently
replace corrupted settings with defaults.

## Workspace coordination

Processing, cleanup, and requeue operations use one non-blocking, OS-backed
workspace lock. The small `.workspace.lock` file holds the actual lock and its
ignored `.workspace.lock.json` companion identifies the active PID, run ID,
start time, and operation. The metadata alone never blocks a new operation: a
stale record is replaced as soon as the OS lock can be acquired.

Processing atomically moves selected inbox files into
`inbox/.processing/<run-id>/` before it begins. Unconsumed files are returned
to the inbox during shutdown or failure. The desktop window requests
cancellation when closed and waits for the active safe boundary; FFmpeg work
and OpenAI retry waits observe that request.
