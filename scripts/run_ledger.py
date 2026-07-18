#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from app_metadata import APP_VERSION
except ImportError:
    from scripts.app_metadata import APP_VERSION

try:
    from atomic_io import InvalidSchemaError, atomic_write_json, load_json, require_json_object, require_known_schema_version
except ImportError:
    from scripts.atomic_io import InvalidSchemaError, atomic_write_json, load_json, require_json_object, require_known_schema_version

try:
    from safe_paths import require_plain_filename
except ImportError:
    from scripts.safe_paths import require_plain_filename


RUN_SCHEMA_VERSION = 3
_SUPPORTED_RUN_SCHEMA_VERSIONS = {2, RUN_SCHEMA_VERSION}


@dataclass(frozen=True)
class NormalizedRunRecord:
    """Stable internal view of one legacy or current run-ledger record."""

    record_type: str
    status: str
    media_names: tuple[str, ...]
    error_message: str | None
    output_dir: Path | None
    transaction_status: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class NormalizedRunLedger:
    """One normalized ledger document for history and recovery consumers."""

    path: Path
    run_id: str
    schema_version: int
    records: tuple[NormalizedRunRecord, ...]


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
    run_id = require_plain_filename(run_id or uuid4().hex)
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
    atomic_write_json(path, payload)
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
            "started_at": started_at,
            "ended_at": ended_at,
            "dry_run": dry_run,
            "targeted": targeted,
        },
        "summary": summarize_records(records),
        "records": records,
    }


def normalize_run_log(log_path: Path) -> dict[str, Any]:
    raw = load_json(log_path, document_name="Run ledger")
    if isinstance(raw, list):
        return _migrate_legacy_array_log(raw, log_path)

    payload = require_json_object(raw, document_name="Run ledger")
    raw_version = payload.get("schema_version", 2)
    require_known_schema_version(
        raw_version,
        document_name="Run ledger",
        supported_versions=_SUPPORTED_RUN_SCHEMA_VERSIONS,
    )
    return _normalize_structured_log(payload, log_path)


def load_normalized_run_ledger(log_path: Path) -> NormalizedRunLedger:
    """Load either supported ledger shape into one recovery-safe record model."""

    payload = normalize_run_log(log_path)
    run = payload["run"]
    return NormalizedRunLedger(
        path=Path(log_path),
        run_id=str(run["run_id"]),
        schema_version=int(payload["schema_version"]),
        records=tuple(_normalize_run_record(record) for record in payload["records"]),
    )


def _migrate_legacy_array_log(records: list[Any], log_path: Path) -> dict[str, Any]:
    if not all(isinstance(record, dict) for record in records):
        raise InvalidSchemaError("Legacy run ledger records must all be JSON objects")
    return _build_normalized_payload(
        records=[dict(record) for record in records],
        run={
            "run_id": _run_id_from_path(log_path),
            "app_version": "legacy",
            "command": "inbox",
            "started_at": None,
            "ended_at": None,
            "dry_run": False,
            "targeted": False,
        },
    )


def _normalize_structured_log(payload: dict[str, Any], log_path: Path) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise InvalidSchemaError("Run ledger records must be a list of JSON objects")

    raw_run = payload.get("run", {})
    if not isinstance(raw_run, dict):
        raise InvalidSchemaError("Run ledger run metadata must be a JSON object")
    run = dict(raw_run)
    run.setdefault("run_id", _run_id_from_path(log_path))
    run.setdefault("app_version", "unknown")
    run.setdefault("command", "inbox")
    run.setdefault("started_at", None)
    run.setdefault("ended_at", None)
    run.setdefault("dry_run", False)
    run.setdefault("targeted", False)
    _validate_run_metadata(run)
    return _build_normalized_payload(records=[dict(record) for record in records], run=run)


def _build_normalized_payload(records: list[dict[str, Any]], run: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RUN_SCHEMA_VERSION,
        "run": run,
        "summary": summarize_records(records),
        "records": records,
    }


def _validate_run_metadata(run: dict[str, Any]) -> None:
    for key in ("run_id", "app_version", "command"):
        if not isinstance(run.get(key), str) or not run[key].strip():
            raise InvalidSchemaError(f"Run ledger run.{key} must be a non-empty string")
    for key in ("started_at", "ended_at"):
        if run.get(key) is not None and not isinstance(run[key], str):
            raise InvalidSchemaError(f"Run ledger run.{key} must be a string or null")
    for key in ("dry_run", "targeted"):
        if not isinstance(run.get(key), bool):
            raise InvalidSchemaError(f"Run ledger run.{key} must be a boolean")


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    processed = sum(1 for record in records if record.get("status") in {"processed", "committed_with_archival_warning"})
    failed = sum(1 for record in records if record.get("status") == "failed")
    dry_run = sum(1 for record in records if record.get("status") == "dry_run")
    archival_warnings = sum(1 for record in records if record.get("status") == "committed_with_archival_warning")
    media = sum(_media_count(record) for record in records)
    sources = sorted({str(record.get("analysis_source")) for record in records if record.get("analysis_source")})
    return {
        "records": len(records),
        "processed": processed,
        "failed": failed,
        "dry_run": dry_run,
        "committed_with_archival_warning": archival_warnings,
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


def _normalize_run_record(record: dict[str, Any]) -> NormalizedRunRecord:
    media_names: list[str] = []
    raw_files = record.get("files")
    if isinstance(raw_files, list):
        media_names.extend(str(item) for item in raw_files if str(item))
    elif record.get("file"):
        media_names.append(str(record["file"]))

    error = str(record.get("error") or record.get("analysis_error") or "").strip()
    message = str(record.get("message") or "").strip()
    if error and message and error != message:
        error = f"{error}: {message}"
    elif not error:
        error = message
    return NormalizedRunRecord(
        record_type=str(record.get("type") or "unknown").strip().lower() or "unknown",
        status=str(record.get("status") or "unknown").strip().lower() or "unknown",
        media_names=tuple(media_names),
        error_message=error or None,
        output_dir=Path(str(record["output_dir"])) if record.get("output_dir") else None,
        transaction_status=str(record.get("transaction_status")).strip().lower()
        if record.get("transaction_status")
        else None,
        raw=dict(record),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
