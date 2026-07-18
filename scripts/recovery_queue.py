#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from recovery_service import RetryPlan, build_retry_plan, filter_retry_plan
except ImportError:
    from scripts.recovery_service import RetryPlan, build_retry_plan, filter_retry_plan


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
    errors: tuple[str, ...] = ()
    plan: RetryPlan | None = None


def build_recovery_queue(logs_dir: Path, inbox_dir: Path, outputs_dir: Path | None = None) -> RecoveryQueue:
    plan = build_retry_plan(_log_paths(logs_dir), inbox_dir, outputs_dir=outputs_dir)
    items = tuple(
        RecoveryItem(
            filename=candidate.filename,
            path=candidate.path,
            media_type=candidate.media_type,
            run_id=", ".join(candidate.run_ids),
            error=candidate.skip_reason or candidate.error,
            available=candidate.available and candidate.skip_reason is None,
        )
        for candidate in plan.candidates
    )
    available = sum(1 for item in items if item.available)
    return RecoveryQueue(
        items=items,
        available_count=available,
        stale_count=len(items) - available,
        errors=plan.errors,
        plan=plan,
    )


def plan_retry_targets(queue: RecoveryQueue, mode: str = "all") -> list[Path]:
    if queue.plan is not None:
        return list(filter_retry_plan(queue.plan, mode=mode).retry_files)
    return [
        item.path
        for item in queue.items
        if item.available and (mode == "all" or item.media_type == mode.removesuffix("s"))
    ]


def format_recovery_queue(queue: RecoveryQueue) -> str:
    if not queue.items:
        lines = ["Recovery Queue: no failed files found."]
        if queue.errors:
            lines.extend(f"- {error}" for error in queue.errors)
        return "\n".join(lines)
    lines = [
        f"Recovery Queue: {queue.available_count} available, {queue.stale_count} stale/missing",
    ]
    for item in queue.items[:20]:
        state = "available" if item.available else "skipped/missing"
        lines.append(f"- [{state}] {item.filename} | run {item.run_id} | {item.error}")
    if len(queue.items) > 20:
        lines.append(f"- ...and {len(queue.items) - 20} more")
    lines.extend(f"- {error}" for error in queue.errors)
    return "\n".join(lines)


def _log_paths(logs_dir: Path) -> list[Path]:
    if not logs_dir.exists():
        return []
    paths = [path for path in logs_dir.glob("inbox-run-*.json") if path.is_file()]
    paths.sort(key=lambda path: path.name, reverse=True)
    return paths
