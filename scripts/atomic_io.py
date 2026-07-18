"""Crash-safe persistence helpers for the app's local JSON documents."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class PersistenceError(RuntimeError):
    """Base class for a local document that could not be read or saved safely."""


class CorruptJsonError(PersistenceError):
    """Raised when a JSON document is unreadable, truncated, or not valid JSON."""


class InvalidSchemaError(PersistenceError):
    """Raised when valid JSON does not match the document shape the app expects."""


class UnknownSchemaVersionError(InvalidSchemaError):
    """Raised when a document was written by a schema version this app does not know."""


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write *text* by replacing the destination only after the temp file is durable.

    The temporary file is deliberately a sibling of the destination so ``os.replace``
    is an atomic same-filesystem operation.  On failure we remove only the temporary
    file created by this call; existing files, including prior temporary files, are
    left untouched for inspection.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=False,
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            _best_effort_fsync(handle.fileno())
        os.replace(temp_path, destination)
        _best_effort_fsync_directory(destination.parent)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialize JSON consistently and save it with :func:`atomic_write_text`."""

    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, text)


def load_json(path: Path, *, document_name: str) -> Any:
    """Load JSON without ever turning corruption into an empty document."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CorruptJsonError(f"Could not read {document_name} at {source}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorruptJsonError(f"{document_name} at {source} is corrupt or truncated: {exc.msg}") from exc


def require_json_object(payload: Any, *, document_name: str) -> dict[str, Any]:
    """Return a shallow copy of a JSON object or raise a user-facing schema error."""

    if not isinstance(payload, dict):
        raise InvalidSchemaError(f"{document_name} must contain a JSON object")
    return dict(payload)


def require_known_schema_version(
    value: Any,
    *,
    document_name: str,
    supported_versions: set[int],
) -> int:
    """Validate a numeric schema version and identify unsupported documents clearly."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidSchemaError(f"{document_name} schema_version must be an integer")
    if value not in supported_versions:
        known = ", ".join(str(version) for version in sorted(supported_versions))
        raise UnknownSchemaVersionError(
            f"{document_name} uses unsupported schema_version {value}; supported versions: {known}"
        )
    return value


def _best_effort_fsync(descriptor: int) -> None:
    """Flush where the current filesystem supports it without breaking portability."""

    try:
        os.fsync(descriptor)
    except OSError:
        pass


def _best_effort_fsync_directory(directory: Path) -> None:
    """Ask POSIX filesystems to persist the rename; Windows safely skips this step."""

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        _best_effort_fsync(descriptor)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
