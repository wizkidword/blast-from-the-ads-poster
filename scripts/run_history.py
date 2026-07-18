#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from run_ledger import load_normalized_run_ledger
except ImportError:
    from scripts.run_ledger import load_normalized_run_ledger

try:
    from recovery_service import build_retry_plan
except ImportError:
    from scripts.recovery_service import build_retry_plan

RUN_LOG_PATTERN = re.compile(r"^inbox-run-(.+)\.json$")


@dataclass(frozen=True)
class RunSummary:
    path: Path
    run_id: str
    status: str
    total_records: int
    media_count: int
    processed_count: int
    failed_count: int
    dry_run_count: int
    analysis_sources: tuple[str, ...]
    error_messages: tuple[str, ...]


@dataclass(frozen=True)
class RunRecord:
    record_type: str
    display_name: str
    status: str
    media_names: tuple[str, ...]
    caption_path: Path | None
    legacy_caption_path: Path | None
    output_dir: Path | None
    manifest_path: Path | None
    processed_media_paths: tuple[Path, ...]
    analysis_source: str
    analysis_error: str | None
    publish_status: str | None
    error_message: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class RunDetails:
    path: Path
    summary: RunSummary
    records: tuple[RunRecord, ...]


def summarize_inbox_run(log_path: Path) -> RunSummary:
    run_id = _run_id_from_path(log_path)
    try:
        normalized = load_normalized_run_ledger(log_path)
        raw_results = [record.raw for record in normalized.records]
    except Exception as exc:
        return RunSummary(
            path=log_path,
            run_id=run_id,
            status="unreadable",
            total_records=0,
            media_count=0,
            processed_count=0,
            failed_count=1,
            dry_run_count=0,
            analysis_sources=(),
            error_messages=(f"Could not read run log: {exc}",),
        )

    records = [item for item in raw_results if isinstance(item, dict)]
    if not records:
        return RunSummary(
            path=log_path,
            run_id=run_id,
            status="empty",
            total_records=0,
            media_count=0,
            processed_count=0,
            failed_count=0,
            dry_run_count=0,
            analysis_sources=(),
            error_messages=(),
        )

    processed_count = 0
    failed_count = 0
    dry_run_count = 0
    archival_warning_count = 0
    media_count = 0
    sources: set[str] = set()
    errors: list[str] = []

    for record in records:
        status = str(record.get("status") or "").strip().lower()
        analysis_source = str(record.get("analysis_source") or "").strip()
        if analysis_source:
            sources.add(analysis_source)

        media_count += _media_count(record)
        if status in {"processed", "committed_with_archival_warning"}:
            processed_count += 1
        if status == "committed_with_archival_warning":
            archival_warning_count += 1
        elif status == "failed":
            failed_count += 1
        elif status == "dry_run":
            dry_run_count += 1

        if status == "failed" or analysis_source == "failed" or record.get("analysis_error"):
            error_message = _record_error_message(record)
            if error_message and error_message not in errors:
                errors.append(error_message)
        for warning in record.get("warnings", []) if isinstance(record.get("warnings"), list) else []:
            if isinstance(warning, str) and warning and warning not in errors:
                errors.append(warning)

    if failed_count:
        status = "failed"
    elif dry_run_count and dry_run_count == len(records):
        status = "dry_run"
    elif errors or archival_warning_count:
        status = "warning"
    else:
        status = "processed"

    return RunSummary(
        path=log_path,
        run_id=run_id,
        status=status,
        total_records=len(records),
        media_count=media_count,
        processed_count=processed_count,
        failed_count=failed_count,
        dry_run_count=dry_run_count,
        analysis_sources=tuple(sorted(sources)),
        error_messages=tuple(errors),
    )


def list_recent_inbox_runs(logs_dir: Path, limit: int = 5) -> list[RunSummary]:
    if not logs_dir.exists():
        return []

    log_paths = [
        path
        for path in logs_dir.iterdir()
        if path.is_file() and RUN_LOG_PATTERN.match(path.name)
    ]
    log_paths.sort(key=_sort_key, reverse=True)
    return [summarize_inbox_run(path) for path in log_paths[:limit]]


def find_latest_run_log(logs_dir: Path) -> Path | None:
    summaries = list_recent_inbox_runs(logs_dir, limit=1)
    return summaries[0].path if summaries else None


def load_inbox_run_details(log_path: Path) -> RunDetails:
    summary = summarize_inbox_run(log_path)
    try:
        raw_results = [record.raw for record in load_normalized_run_ledger(log_path).records]
    except Exception:
        raw_results = []

    records = []
    for item in raw_results if isinstance(raw_results, list) else []:
        if isinstance(item, dict):
            records.append(_build_run_record(item))
    return RunDetails(path=log_path, summary=summary, records=tuple(records))


def format_run_summary(summary: RunSummary, latest: bool = False) -> str:
    label = "Latest Run" if latest else summary.run_id
    parts = [
        f"{label}: {summary.status.upper()}",
        f"{summary.processed_count} processed",
        f"{summary.failed_count} failed",
        f"{summary.media_count} media",
    ]
    if summary.analysis_sources:
        parts.append("sources: " + ", ".join(summary.analysis_sources))
    if summary.error_messages:
        parts.append(summary.error_messages[0])
    return " | ".join(parts)


def format_run_history(summaries: Iterable[RunSummary]) -> str:
    items = list(summaries)
    if not items:
        return "Latest Run: none yet"

    lines = []
    for index, summary in enumerate(items):
        lines.append(format_run_summary(summary, latest=index == 0))
    return "\n".join(lines)


def format_run_details(details: RunDetails) -> str:
    summary = details.summary
    lines = [
        f"Run {summary.run_id}: {summary.status.upper()}",
        f"Records: {summary.total_records} | Processed: {summary.processed_count} | Failed: {summary.failed_count} | Media: {summary.media_count}",
    ]
    if summary.analysis_sources:
        lines.append("Analysis sources: " + ", ".join(summary.analysis_sources))
    if summary.error_messages:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {message}" for message in summary.error_messages)

    if details.records:
        lines.extend(["", "Items:"])
    for index, record in enumerate(details.records, start=1):
        line = f"{index}. [{record.status.upper()}] {record.record_type}: {record.display_name}"
        if record.analysis_source:
            line += f" | source: {record.analysis_source}"
        if record.publish_status:
            line += f" | publish: {record.publish_status}"
        lines.append(line)
        if record.caption_path:
            lines.append(f"   caption: {record.caption_path}")
        if record.output_dir:
            lines.append(f"   output: {record.output_dir}")
        if record.error_message:
            lines.append(f"   error: {record.error_message}")

    if summary.failed_count:
        lines.extend(["", "Recovery:", "- Retry from inbox for failed files that are still present."])
    return "\n".join(lines)


def collect_failed_retry_candidates(log_path: Path, inbox_dir: Path) -> list[Path]:
    return list(build_retry_plan([log_path], inbox_dir).retry_files)


def _run_id_from_path(log_path: Path) -> str:
    match = RUN_LOG_PATTERN.match(log_path.name)
    return match.group(1) if match else log_path.stem


def _sort_key(log_path: Path) -> tuple[float, str]:
    try:
        modified_at = log_path.stat().st_mtime
    except OSError:
        modified_at = 0.0
    return modified_at, log_path.name


def _media_count(record: dict[str, Any]) -> int:
    if isinstance(record.get("file_count"), int):
        return max(0, int(record["file_count"]))
    files = record.get("files")
    if isinstance(files, list):
        return len(files)
    if record.get("file"):
        return 1
    return 0


def _record_error_message(record: dict[str, Any]) -> str:
    error = str(record.get("error") or record.get("analysis_error") or "").strip()
    message = str(record.get("message") or "").strip()
    if error and message and message != error:
        return f"{error}: {message}"
    if error:
        return error
    if message:
        return message
    return "Unknown processing failure"


def _build_run_record(record: dict[str, Any]) -> RunRecord:
    media_names = _media_names(record)
    display_name = ", ".join(media_names) if media_names else str(record.get("type") or "run")
    processed_paths = []
    if record.get("processed_media_path"):
        processed_paths.append(Path(str(record["processed_media_path"])))
    for path in record.get("processed_media_paths") or []:
        if path:
            processed_paths.append(Path(str(path)))

    status = str(record.get("status") or "unknown").strip().lower()
    error_message = None
    if status == "failed" or record.get("analysis_error"):
        error_message = _record_error_message(record)

    return RunRecord(
        record_type=str(record.get("type") or "unknown"),
        display_name=display_name,
        status=status,
        media_names=tuple(media_names),
        caption_path=_optional_path(record.get("caption_path")),
        legacy_caption_path=_optional_path(record.get("legacy_caption_path")),
        output_dir=_optional_path(record.get("output_dir")),
        manifest_path=_optional_path(record.get("manifest_path")),
        processed_media_paths=tuple(processed_paths),
        analysis_source=str(record.get("analysis_source") or ""),
        analysis_error=str(record.get("analysis_error")) if record.get("analysis_error") else None,
        publish_status=str(record.get("publish_status")) if record.get("publish_status") else None,
        error_message=error_message,
        raw=record,
    )


def _media_names(record: dict[str, Any]) -> list[str]:
    files = record.get("files")
    if isinstance(files, list):
        return [str(item) for item in files if str(item)]
    if record.get("file"):
        return [str(record["file"])]
    return []


def _optional_path(value: Any) -> Path | None:
    if not value:
        return None
    return Path(str(value))
