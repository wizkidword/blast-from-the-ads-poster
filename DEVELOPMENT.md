# Development

## Supported environment

- Windows 10/11
- Python 3.13
- FFmpeg and FFprobe on `PATH` for live media processing

## Setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-windows-py313.txt
Copy-Item .env.example .env
Copy-Item settings.example.json settings.json
```

Add `OPENAI_API_KEY` to the local `.env` file only when running real media
analysis. The test suite does not need an API key or real input media.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe scripts\workflow.py setup
cmd /c Verify-Release.bat
```

The setup command checks the active local media configuration, while the
release command is self-contained and does not read local `settings.json`.
GitHub Actions runs the unit suite on Windows with Python 3.13, then rebuilds
the standalone EXE from the same lock and runs its headless smoke-test mode.

## Workstation paths

`settings.example.json` is the safe-to-share template. Copy it to the ignored
local `settings.json` before running the live setup check, then update the two
media-directory values in the Settings tab (or leave them blank for the local
`captions/` and `!processed/` folders). The configured drive must be mounted
and writable. Each operation builds one validated directory context from
`settings.json`; it rejects missing, file-valued, overlapping, nested, or
non-writable managed folders before it moves or creates media.

Saving settings validates the selected folders before writing the new values.
The desktop app uses the resulting context immediately, so no restart is
needed for processing, status, review, recovery, or export to use the new
caption and processed-media locations.

## Reproducible release build

`Setup-Environment.bat`, `Build-Standalone-Exe.bat`,
`Verify-Release.bat`, and the desktop launcher all use the same CPython 3.13
virtual environment and `requirements-windows-py313.txt` lock. The setup step
re-applies the lock even when `.venv` already exists, so a stale dependency
cannot silently build the executable.

Each standalone build writes `dist/release-metadata/SHA256SUMS.txt` and
`dist/release-metadata/sbom.spdx.json`. Executable signing remains a separate
release step because it requires signing credentials that are intentionally not
stored in this repository.

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
