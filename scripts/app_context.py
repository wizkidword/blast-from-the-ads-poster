"""One validated, immutable directory configuration for a local app operation."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from app_paths import get_project_root
except ImportError:
    from scripts.app_paths import get_project_root

try:
    from settings_store import AppSettings, load_settings, resolve_configured_dir
except ImportError:
    from scripts.settings_store import AppSettings, load_settings, resolve_configured_dir


class AppContextError(ValueError):
    """Raised when configured folders cannot safely support an app operation."""


@dataclass(frozen=True)
class AppContext:
    project_dir: Path
    settings_path: Path
    settings: AppSettings
    inbox_dir: Path
    captions_dir: Path
    processed_dir: Path
    outputs_dir: Path
    logs_dir: Path
    exports_dir: Path
    temp_dir: Path

    @property
    def output_dir(self) -> Path:
        """Compatibility spelling for callers that use singular output_dir."""

        return self.outputs_dir


def build_app_context(
    project_dir: Path | None = None,
    *,
    settings_path: Path | None = None,
    settings: AppSettings | None = None,
) -> AppContext:
    """Resolve settings into one context without creating or mutating directories."""

    root = Path(project_dir or get_project_root()).resolve()
    resolved_settings_path = Path(settings_path or (root / "settings.json"))
    active_settings = settings if settings is not None else load_settings(resolved_settings_path)
    return AppContext(
        project_dir=root,
        settings_path=resolved_settings_path,
        settings=active_settings,
        inbox_dir=root / "inbox",
        captions_dir=resolve_configured_dir(root, active_settings.captions_dir, "captions"),
        processed_dir=resolve_configured_dir(root, active_settings.processed_dir, "!processed"),
        outputs_dir=root / "outputs",
        logs_dir=root / "logs",
        exports_dir=root / "exports",
        temp_dir=root / "temp",
    )


def prepare_app_context(context: AppContext) -> AppContext:
    """Create, validate, and prove writability of every managed operation directory."""

    directories = _managed_directories(context)
    _validate_distinct_layout(directories)
    for role, directory in directories.items():
        path = Path(directory)
        if path.exists() and not path.is_dir():
            raise AppContextError(f"{role} path must be a directory, not a file: {path}")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppContextError(f"{role} directory cannot be created: {path} ({exc})") from exc
        if not path.is_dir():
            raise AppContextError(f"{role} path must be a directory, not a file: {path}")
        _require_writable(role, path)
    return context


def _managed_directories(context: AppContext) -> dict[str, Path]:
    return {
        "inbox": context.inbox_dir,
        "captions": context.captions_dir,
        "processed media": context.processed_dir,
        "outputs": context.outputs_dir,
        "run logs": context.logs_dir,
        "posting packs": context.exports_dir,
        "temporary work": context.temp_dir,
    }


def _validate_distinct_layout(directories: dict[str, Path]) -> None:
    items = [(role, Path(path).resolve()) for role, path in directories.items()]
    for index, (role, path) in enumerate(items):
        for other_role, other_path in items[index + 1 :]:
            if path == other_path:
                raise AppContextError(f"{role} and {other_role} cannot use the same directory: {path}")
            if _is_within(path, other_path) or _is_within(other_path, path):
                raise AppContextError(
                    f"{role} and {other_role} cannot be nested inside one another: {path} / {other_path}"
                )


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def _require_writable(role: str, directory: Path) -> None:
    descriptor: int | None = None
    temp_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=".blast-write-check-", dir=directory)
        temp_path = Path(raw_path)
        os.write(descriptor, b"ok")
        os.fsync(descriptor)
    except OSError as exc:
        raise AppContextError(f"{role} directory is not writable: {directory} ({exc})") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
