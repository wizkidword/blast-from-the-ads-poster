"""Structural filesystem-boundary checks for workspace operations.

Persisted manifests and run ledgers are input, not authority.  Callers must
resolve a value against the root that owns it immediately before an operation
that can read, copy, move, replace, or delete a filesystem entry.
"""
from __future__ import annotations

import re
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when an untrusted filesystem value is outside its approved root."""


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_WINDOWS_ABSOLUTE_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_WINDOWS_DEVICE_PREFIXES = ("\\\\?\\", "\\\\.\\", "//?/", "//./")


def resolve_existing_under(root: Path, raw_path: str | Path) -> Path:
    """Resolve an existing candidate and prove it remains below ``root``.

    A legacy absolute path is accepted only when its resolved location is still
    contained by the supplied root.  Relative values may not traverse upward.
    """

    root_path = _resolved_root(root)
    candidate = _candidate(root_path, raw_path)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"Path does not exist under approved root: {raw_path!s}") from exc
    return _require_under(root_path, resolved)


def resolve_output_under(root: Path, raw_path: str | Path) -> Path:
    """Resolve an output candidate through an existing safe parent below ``root``.

    The returned path is safe to create only while callers revalidate it just
    before mutation.  Resolving the nearest existing ancestor prevents a
    symlink or Windows junction from redirecting a later write outside root.
    """

    root_path = _resolved_root(root)
    candidate = _candidate(root_path, raw_path)
    existing_parent, missing_parts = _nearest_existing_parent(candidate)
    safe_parent = _require_under(root_path, existing_parent.resolve(strict=True))
    result = safe_parent
    for part in reversed(missing_parts):
        result = result / part
    return _require_under(root_path, result.resolve(strict=False))


def normalize_relative_to(root: Path, path: Path) -> str:
    """Return a normalized, portable relative representation for persisted state."""

    root_path = _resolved_root(root)
    try:
        resolved = Path(path).resolve(strict=Path(path).exists())
    except OSError as exc:
        raise UnsafePathError(f"Could not resolve path for persistence: {path!s}") from exc
    safe_path = _require_under(root_path, resolved)
    relative = safe_path.relative_to(root_path)
    return relative.as_posix() or "."


def require_plain_filename(raw_name: str) -> str:
    """Validate a value that is semantically a filename, not a path."""

    value = _coerce_text(raw_name, label="filename")
    if value in {".", ".."}:
        raise UnsafePathError("Filename must not be a traversal component")
    if "/" in value or "\\" in value:
        raise UnsafePathError("Filename must not contain path separators")
    if ":" in value:
        raise UnsafePathError("Filename must not contain a drive or alternate data stream separator")
    if _WINDOWS_DRIVE.match(value) or value.startswith(_WINDOWS_DEVICE_PREFIXES):
        raise UnsafePathError("Filename must not use a Windows drive or device path")
    return value


def _resolved_root(root: Path) -> Path:
    root_path = Path(root)
    try:
        resolved = root_path.resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"Approved root does not exist: {root_path}") from exc
    if not resolved.is_dir():
        raise UnsafePathError(f"Approved root is not a directory: {root_path}")
    return resolved


def _candidate(root: Path, raw_path: str | Path) -> Path:
    value = _coerce_text(raw_path, label="path")
    absolute = _validate_path_text(value)
    return Path(value) if absolute else root / Path(value)


def _coerce_text(raw_value: str | Path, *, label: str) -> str:
    value = str(raw_value)
    if not value or not value.strip():
        raise UnsafePathError(f"{label.capitalize()} must not be empty")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise UnsafePathError(f"{label.capitalize()} must not contain NUL, line-break, or control characters")
    return value


def _validate_path_text(value: str) -> bool:
    if value.startswith(_WINDOWS_DEVICE_PREFIXES):
        raise UnsafePathError("Windows device paths are not allowed")
    if value.startswith(("\\\\", "//")):
        raise UnsafePathError("UNC paths are not allowed")

    if _WINDOWS_DRIVE.match(value):
        if not _WINDOWS_ABSOLUTE_DRIVE.match(value):
            raise UnsafePathError("Drive-relative paths are not allowed")
        if ":" in value[2:]:
            raise UnsafePathError("Alternate data stream syntax is not allowed")
        absolute = True
    else:
        if ":" in value:
            raise UnsafePathError("Alternate data stream syntax is not allowed")
        absolute = value.startswith(("/", "\\")) or Path(value).is_absolute()

    parts = value.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise UnsafePathError("Parent-directory traversal is not allowed")
    return absolute


def _nearest_existing_parent(candidate: Path) -> tuple[Path, list[str]]:
    current = candidate
    missing_parts: list[str] = []
    while not current.exists():
        parent = current.parent
        if parent == current:
            raise UnsafePathError(f"No existing parent is available for output path: {candidate}")
        missing_parts.append(current.name)
        current = parent
    return current, missing_parts


def _require_under(root: Path, candidate: Path) -> Path:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes approved root: {candidate}") from exc
    return candidate
