#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

try:
    from app_metadata import APP_VERSION
except ImportError:
    from scripts.app_metadata import APP_VERSION


RUN_SCHEMA_VERSION = 2


def write_run_ledger(
    logs_dir: Path,
    records: list[dict[str, Any]],
    command: str,
    dry_run: bool = False,
    targeted: bool = False,
    run_id: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or str(int(time.time()))
    payload = build_run_ledger(
        records=records,
        command=command,
        dry_run=dry_run,
        targeted=targeted,
        run_id=run_id,
        started_at=started_at,
        ended_at=ended_at,
    )
    path = logs_dir / f"inbox-run-{run_id}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_run_ledger(
    records: list[dict[str, Any]],
    command: str,
    dry_run: bool,
    targeted: bool,
    run_id: str,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "app_version": APP_VERSION,
            "command": command,
            "started_at": started_at or _unix_iso(),
            "ended_at": ended_at or _unix_iso(),
            "dry_run": dry_run,
            "targeted": targeted,
        },
        "summary": summarize_records(records),
        "records": records,
    }


def normalize_run_log(log_path: Path) -> dict[str, Any]:
    raw = json.loads(log_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("records"), list):
        payload = dict(raw)
        payload.setdefault("schema_version", RUN_SCHEMA_VERSION)
        payload.setdefault("run", {})
        payload["run"].setdefault("run_id", _run_id_from_path(log_path))
        payload["run"].setdefault("app_version", "unknown")
        payload["run"].setdefault("command", "inbox")
        payload["run"].setdefault("dry_run", False)
        payload["run"].setdefault("targeted", False)
        payload["summary"] = summarize_records([record for record in payload["records"] if isinstance(record, dict)])
        return payload
    if isinstance(raw, list):
        records = [record for record in raw if isinstance(record, dict)]
        return {
            "schema_version": 1,
            "run": {
                "run_id": _run_id_from_path(log_path),
                "app_version": "legacy",
                "command": "inbox",
                "started_at": None,
                "ended_at": None,
                "dry_run": False,
                "targeted": False,
            },
            "summary": summarize_records(records),
            "records": records,
        }
    raise ValueError("run log must be a structured object or legacy JSON list")


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    processed = sum(1 for record in records if record.get("status") == "processed")
    failed = sum(1 for record in records if record.get("status") == "failed")
    dry_run = sum(1 for record in records if record.get("status") == "dry_run")
    media = sum(_media_count(record) for record in records)
    sources = sorted({str(record.get("analysis_source")) for record in records if record.get("analysis_source")})
    return {
        "records": len(records),
        "processed": processed,
        "failed": failed,
        "dry_run": dry_run,
        "media": media,
        "analysis_sources": sources,
    }


def _media_count(record: dict[str, Any]) -> int:
    if isinstance(record.get("file_count"), int):
        return int(record["file_count"])
    if isinstance(record.get("files"), list):
        return len(record["files"])
    if record.get("file"):
        return 1
    return 0


def _run_id_from_path(log_path: Path) -> str:
    stem = log_path.stem
    return stem.removeprefix("inbox-run-")


def _unix_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
