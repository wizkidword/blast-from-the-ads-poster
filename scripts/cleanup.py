#!/usr/bin/env python3
from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from safe_paths import UnsafePathError, resolve_existing_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, resolve_existing_under

try:
    from workspace_lock import WorkspaceLock
except ImportError:
    from scripts.workspace_lock import WorkspaceLock


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
    base_dir = resolve_existing_under(base_dir, base_dir)
    items: list[CleanupItem] = []

    if settings.clean_temp_frames:
        frames_dir = _safe_existing_path(base_dir, base_dir / "temp" / "frames")
        if frames_dir and frames_dir.is_dir():
            for path in frames_dir.iterdir():
                if path.is_file():
                    safe_path = _safe_existing_path(base_dir, path)
                    if safe_path:
                        items.append(CleanupItem(path=safe_path, reason="temporary video frame"))

    _add_old_files(items, base_dir, base_dir / "logs", "inbox-run-*.json", settings.logs_retention_days, now, "old run log")
    _add_old_pack_dirs(items, base_dir, base_dir / "exports" / "posting-packs", settings.exports_retention_days, now)
    _add_old_orphan_output_dirs(items, base_dir, base_dir / "outputs", settings.orphan_outputs_retention_days, now)

    return CleanupPlan(base_dir=base_dir, items=tuple(_dedupe_items(items)))


def execute_cleanup(plan: CleanupPlan) -> CleanupResult:
    try:
        base_dir = resolve_existing_under(plan.base_dir, plan.base_dir)
    except UnsafePathError:
        return CleanupResult(deleted_count=0, failed_count=len(plan.items), deleted_paths=())
    with WorkspaceLock(base_dir, "safe cleanup"):
        return _execute_cleanup(plan, base_dir)


def _execute_cleanup(plan: CleanupPlan, base_dir: Path) -> CleanupResult:
    deleted: list[Path] = []
    failed = 0
    for item in plan.items:
        try:
            target = resolve_existing_under(base_dir, item.path)
            if target == base_dir or _is_active_processing_target(base_dir, target) or _is_protected_workspace(base_dir, target):
                failed += 1
                continue
            if target.is_dir():
                target = resolve_existing_under(base_dir, target)
                shutil.rmtree(target)
            else:
                target = resolve_existing_under(base_dir, target)
                target.unlink(missing_ok=True)
            deleted.append(target)
        except (OSError, UnsafePathError):
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


def _add_old_files(items: list[CleanupItem], base_dir: Path, folder: Path, pattern: str, age_days: int, now: float, reason: str) -> None:
    folder = _safe_existing_path(base_dir, folder)
    if age_days <= 0 or not folder or not folder.is_dir():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.glob(pattern):
        safe_path = _safe_existing_path(base_dir, path)
        if safe_path and safe_path.is_file() and _mtime(safe_path) < cutoff:
            items.append(CleanupItem(path=safe_path, reason=reason))


def _add_old_pack_dirs(items: list[CleanupItem], base_dir: Path, folder: Path, age_days: int, now: float) -> None:
    folder = _safe_existing_path(base_dir, folder)
    if age_days <= 0 or not folder or not folder.is_dir():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.iterdir():
        safe_path = _safe_existing_path(base_dir, path)
        if safe_path and safe_path.is_dir() and _tree_content_mtime(safe_path) < cutoff:
            items.append(CleanupItem(path=safe_path, reason="old posting pack"))


def _add_old_orphan_output_dirs(items: list[CleanupItem], base_dir: Path, folder: Path, age_days: int, now: float) -> None:
    folder = _safe_existing_path(base_dir, folder)
    if age_days <= 0 or not folder or not folder.is_dir():
        return
    cutoff = now - (age_days * 86400)
    for path in folder.iterdir():
        safe_path = _safe_existing_path(base_dir, path)
        if not safe_path or not safe_path.is_dir() or (safe_path / "post_manifest.json").exists():
            continue
        if _tree_content_mtime(safe_path) < cutoff:
            items.append(CleanupItem(path=safe_path, reason="old orphan output folder"))


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


def _safe_existing_path(base_dir: Path, path: Path) -> Path | None:
    try:
        return resolve_existing_under(base_dir, path)
    except UnsafePathError:
        return None


def _is_active_processing_target(base_dir: Path, target: Path) -> bool:
    active_roots = (base_dir / ".processing", base_dir / "inbox" / ".processing", base_dir / "outputs" / ".processing")
    return any(_is_same_or_under(target, active_root) for active_root in active_roots)


def _is_protected_workspace(base_dir: Path, target: Path) -> bool:
    outputs_dir = base_dir / "outputs"
    if target.parent != outputs_dir or not target.is_dir():
        return False
    # A folder with a manifest is a workspace, not an orphan cleanup target.
    # Treat both valid and malformed manifests as protected until a dedicated
    # recovery workflow can validate them.
    return (target / "post_manifest.json").exists()


def _is_same_or_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
