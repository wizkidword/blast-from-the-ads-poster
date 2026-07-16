from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional


def parse_limit_value(raw: str) -> Optional[int]:
    value = raw.strip()
    if not value:
        return None
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("Limit must be a positive whole number.")
    return int(value)


def format_workflow_label(action: str, limit: Optional[int], dry_run: bool, target_files: Optional[List[Path]]) -> str:
    if action == "setup":
        return "Running: setup"
    if dry_run:
        return f"Running: inbox --dry-run{' --limit ' + str(limit) if limit else ''}"
    if target_files:
        return f"Running: inbox targeted retry for {len(target_files)} file(s)"
    return f"Running: inbox{' --limit ' + str(limit) if limit else ''}"


def run_workflow_action(
    action: str,
    limit: Optional[int],
    dry_run: bool,
    target_files: Optional[List[Path]],
    setup_check_func: Callable[[], int],
    run_inbox_processing_func: Callable[..., list[dict]],
    has_failed_results_func: Callable[[list[dict]], bool],
) -> int:
    if action == "setup":
        return setup_check_func()
    if action == "inbox":
        summary = run_inbox_processing_func(limit=limit, dry_run=dry_run, target_files=target_files)
        return 1 if has_failed_results_func(summary) else 0
    print(f"ERROR: Unknown action '{action}'")
    return 1
