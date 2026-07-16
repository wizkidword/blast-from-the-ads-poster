#!/usr/bin/env python3
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CleanupSettings:
    logs_retention_days: int = 90
    exports_retention_days: int = 30
    orphan_outputs_retention_days: int = 14
    clean_temp_frames: bool = True


@dataclass(frozen=True)
class CleanupItem:
    path: Path
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    base_dir: Path
    items: tuple[CleanupItem, ...]


@dataclass(frozen=True)
class CleanupResult:
    deleted_count: int
    failed_count: int
    deleted_paths: tuple[Path, ...]


def plan_cleanup(base_dir: Path, settings: CleanupSettings | None = None, now: float | None = None) -> CleanupPlan:
    settings = settings or CleanupSettings()
    now = time.time() if now is None else now
    items: list[CleanupItem] = []

    if settings.clean_temp_frames:
        frames_dir = base_dir / "temp" / "frames"
        if frames_dir.exists():
            for path in frames_dir.iterdir():
                if path.is_file():
                    items.append(CleanupItem(path=path, reason="temporary video frame"))

    _add_old_files(items, base_dir / "logs", "inbox-run-*.json", settings.logs_retention_days, now, "old run log")
    _add_old_pack_dirs(items, base_dir / "exports" / "posting-packs", settings.exports_retention_days, now)
    _add_old_orphan_output_dirs(items, base_dir / "outputs", settings.orphan_outputs_retention_days, now)

    return CleanupPlan(base_dir=base_dir, items=tuple(_dedupe_items(items)))


def execute_cleanup(plan: CleanupPlan) -> CleanupResult:
    deleted: list[Path] = []
    failed = 0
    base_dir = plan.base_dir.resolve()
    for item in plan.items:
        try:
            target = item.path.resolve()
            if not str(target).lower().startswith(str(base_dir).lower()):
                failed += 1
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            deleted.append(target)
        except OSError:
            failed += 1
    return CleanupResult(deleted_count=len(deleted), failed_count=failed, deleted_paths=tuple(deleted))


def format_cleanup_plan(plan: CleanupPlan) -> str:
    if not plan.items:
        return "Cleanup: no safe retention targets found."
    lines = [f"Cleanup: {len(plan.items)} item(s) ready"]
    for item in plan.items[:20]:
        lines.append(f"- {item.reason}: {item.path}")
    if len(plan.items) > 20:
        lines.append(f"- ...and {len(plan.items) - 20} more")
    return "\n".join(lines)


def _add_old_files(items: list[CleanupItem], folder: Path, pattern: str, age_days: int, now: float, reason: str) -> None:
    if age_days <= 0 or not folder.exists():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.glob(pattern):
        if path.is_file() and _mtime(path) < cutoff:
            items.append(CleanupItem(path=path, reason=reason))


def _add_old_pack_dirs(items: list[CleanupItem], folder: Path, age_days: int, now: float) -> None:
    if age_days <= 0 or not folder.exists():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.iterdir():
        if path.is_dir() and _tree_content_mtime(path) < cutoff:
            items.append(CleanupItem(path=path, reason="old posting pack"))


def _add_old_orphan_output_dirs(items: list[CleanupItem], folder: Path, age_days: int, now: float) -> None:
    if age_days <= 0 or not folder.exists():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.iterdir():
        if not path.is_dir() or (path / "post_manifest.json").exists():
            continue
        if _tree_content_mtime(path) < cutoff:
            items.append(CleanupItem(path=path, reason="old orphan output folder"))


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _tree_content_mtime(path: Path) -> float:
    newest = 0.0
    if path.is_file():
        return _mtime(path)
    for child in path.rglob("*"):
        if child.is_file():
            newest = max(newest, _mtime(child))
    return newest or _mtime(path)


def _dedupe_items(items: list[CleanupItem]) -> list[CleanupItem]:
    deduped: list[CleanupItem] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.path).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
