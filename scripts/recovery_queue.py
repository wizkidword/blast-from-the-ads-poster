#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from media_rules import is_supported_media_file, is_video_file
except ImportError:
    from scripts.media_rules import is_supported_media_file, is_video_file

try:
    from run_ledger import normalize_run_log
except ImportError:
    from scripts.run_ledger import normalize_run_log

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under


@dataclass(frozen=True)
class RecoveryItem:
    filename: str
    path: Path
    media_type: str
    run_id: str
    error: str
    available: bool


@dataclass(frozen=True)
class RecoveryQueue:
    items: tuple[RecoveryItem, ...]
    available_count: int
    stale_count: int


def build_recovery_queue(logs_dir: Path, inbox_dir: Path) -> RecoveryQueue:
    items: list[RecoveryItem] = []
    seen: set[tuple[str, str]] = set()
    for log_path in _log_paths(logs_dir):
        try:
            payload = normalize_run_log(log_path)
        except Exception:
            continue
        run_id = str(payload.get("run", {}).get("run_id") or log_path.stem)
        for record in payload.get("records", []):
            if not isinstance(record, dict) or str(record.get("status", "")).lower() != "failed":
                continue
            for raw_filename in _record_filenames(record):
                try:
                    filename = require_plain_filename(raw_filename)
                    path = resolve_output_under(inbox_dir, filename)
                    available = path.exists() and resolve_existing_under(inbox_dir, path).is_file() and is_supported_media_file(path)
                    error = _record_error(record)
                except UnsafePathError as exc:
                    filename = "unsafe ledger path"
                    path = inbox_dir
                    available = False
                    error = f"Unsafe ledger filename refused: {exc}"
                key = (run_id, filename.lower())
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    RecoveryItem(
                        filename=filename,
                        path=path,
                        media_type="video" if is_video_file(path) else "image",
                        run_id=run_id,
                        error=error,
                        available=available,
                    )
                )
    available = sum(1 for item in items if item.available)
    return RecoveryQueue(items=tuple(items), available_count=available, stale_count=len(items) - available)


def plan_retry_targets(queue: RecoveryQueue, mode: str = "all") -> list[Path]:
    selected: list[Path] = []
    for item in queue.items:
        if not item.available:
            continue
        if mode == "videos" and item.media_type != "video":
            continue
        if mode == "images" and item.media_type != "image":
            continue
        if item.path not in selected:
            selected.append(item.path)
    return selected


def format_recovery_queue(queue: RecoveryQueue) -> str:
    if not queue.items:
        return "Recovery Queue: no failed files found."
    lines = [
        f"Recovery Queue: {queue.available_count} available, {queue.stale_count} stale/missing",
    ]
    for item in queue.items[:20]:
        state = "available" if item.available else "missing"
        lines.append(f"- [{state}] {item.filename} | run {item.run_id} | {item.error}")
    if len(queue.items) > 20:
        lines.append(f"- ...and {len(queue.items) - 20} more")
    return "\n".join(lines)


def _log_paths(logs_dir: Path) -> list[Path]:
    if not logs_dir.exists():
        return []
    paths = [path for path in logs_dir.glob("inbox-run-*.json") if path.is_file()]
    paths.sort(key=lambda path: path.name, reverse=True)
    return paths


def _record_filenames(record: dict) -> list[str]:
    if isinstance(record.get("files"), list):
        return [str(item) for item in record["files"] if str(item)]
    if record.get("file"):
        return [str(record["file"])]
    return []


def _record_error(record: dict) -> str:
    error = str(record.get("error") or record.get("analysis_error") or "").strip()
    message = str(record.get("message") or "").strip()
    if error and message and error != message:
        return f"{error}: {message}"
    return error or message or "failed"
