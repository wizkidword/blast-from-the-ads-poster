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
mounted and writable; strict runtime settings validation is scheduled for
WP-03.
