"""Cross-process workspace coordination for mutating local operations.

The lock file and its JSON metadata companion are deliberately kept in the
project workspace. The operating-system lock is the source of truth, so a
left-over metadata record can never block a new run.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable
from uuid import uuid4


LOCK_FILENAME = ".workspace.lock"
METADATA_FILENAME = ".workspace.lock.json"
_LOCK_MARKER = b"\0"


class WorkspaceLockError(RuntimeError):
    """Base error for workspace coordination failures."""


class WorkspaceBusyError(WorkspaceLockError):
    """Raised when another process still owns the workspace lock."""

    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        self.metadata = metadata or {}
        operation = str(self.metadata.get("operation") or "another operation")
        pid = self.metadata.get("pid")
        run_id = self.metadata.get("run_id")
        started_at = self.metadata.get("started_at")
        details = []
        if pid:
            details.append(f"PID {pid}")
        if run_id:
            details.append(f"run {run_id}")
        if started_at:
            details.append(f"started {started_at}")
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(f"Workspace is busy: {operation} is already running{suffix}.")


class OperationCancelled(WorkspaceLockError):
    """Raised at a safe boundary after the user asks an operation to stop."""


class CancellationToken:
    """Small, thread-safe cancellation signal for a long-running operation."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    def is_requested(self) -> bool:
        return self._event.is_set()

    def raise_if_requested(self) -> None:
        if self.is_requested():
            raise OperationCancelled("Cancellation requested. The current safe step has stopped.")


@dataclass(frozen=True)
class InboxClaim:
    """An inbox source atomically moved into a run-owned processing folder."""

    original_path: Path
    claimed_path: Path
    run_id: str

    def release(self) -> bool:
        """Return an unconsumed source to inbox without overwriting a new file."""

        if not self.claimed_path.exists():
            return True
        if self.original_path.exists():
            return False
        self.original_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(self.claimed_path, self.original_path)
        except OSError:
            return False
        _remove_empty_claim_dirs(self.claimed_path.parent, self.original_path.parent / ".processing")
        return True


class WorkspaceLock(AbstractContextManager["WorkspaceLock"]):
    """A non-blocking, OS-backed exclusive lock for one project workspace."""

    def __init__(self, workspace_dir: Path, operation: str, *, run_id: str | None = None) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.operation = operation
        self.run_id = run_id or uuid4().hex
        self.path = self.workspace_dir / LOCK_FILENAME
        self.metadata_path = self.workspace_dir / METADATA_FILENAME
        self._handle: BinaryIO | None = None
        self._acquired = False

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "pid": os.getpid(),
            "run_id": self.run_id,
            "operation": self.operation,
            "started_at": _utc_now_iso(),
        }

    def acquire(self) -> "WorkspaceLock":
        if self._acquired:
            return self
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            _ensure_lock_marker(handle)
            _try_acquire_os_lock(handle)
        except OSError as exc:
            handle.close()
            if _is_contention_error(exc):
                raise WorkspaceBusyError(read_lock_metadata(self.path)) from None
            raise WorkspaceLockError(f"Could not acquire workspace lock at {self.path}: {exc}") from exc
        try:
            _write_metadata(self.metadata_path, self.metadata)
        except (OSError, WorkspaceLockError) as exc:
            _release_os_lock(handle)
            handle.close()
            raise WorkspaceLockError(f"Could not write workspace lock metadata at {self.path}: {exc}") from exc
        self._handle = handle
        self._acquired = True
        return self

    def release(self) -> None:
        if not self._handle:
            return
        try:
            _release_os_lock(self._handle)
        finally:
            self._handle.close()
            self._handle = None
            self._acquired = False

    def __enter__(self) -> "WorkspaceLock":
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def read_lock_metadata(lock_path: Path) -> dict[str, Any]:
    """Read informational metadata only; callers must still attempt the OS lock."""

    try:
        metadata_path = Path(lock_path).with_name(METADATA_FILENAME)
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def claim_inbox_files(inbox_dir: Path, sources: Iterable[Path], run_id: str) -> list[InboxClaim]:
    """Atomically claim source files by same-filesystem rename into .processing.

    A second claimant cannot overwrite the first claim: once the original name
    has moved, its rename fails.  Already claimed files are returned to inbox if
    a later claim fails.
    """

    inbox_dir = Path(inbox_dir).resolve()
    claim_dir = inbox_dir / ".processing" / run_id
    claim_dir.mkdir(parents=True, exist_ok=True)
    claims: list[InboxClaim] = []
    try:
        for raw_source in sources:
            source = Path(raw_source).resolve()
            try:
                relative = source.relative_to(inbox_dir)
            except ValueError as exc:
                raise WorkspaceLockError(f"Inbox claim refused for path outside inbox: {source}") from exc
            if relative.parent != Path(".") or not source.is_file():
                raise WorkspaceLockError(f"Inbox claim requires an existing top-level media file: {source}")
            destination = claim_dir / source.name
            if destination.exists():
                raise WorkspaceLockError(f"Source claim already exists for {source.name}")
            try:
                os.rename(source, destination)
            except FileNotFoundError as exc:
                raise WorkspaceLockError(f"Source was already claimed or removed: {source.name}") from exc
            except FileExistsError as exc:
                raise WorkspaceLockError(f"Source claim already exists for {source.name}") from exc
            claims.append(InboxClaim(original_path=source, claimed_path=destination, run_id=run_id))
    except Exception:
        for claim in reversed(claims):
            claim.release()
        raise
    return claims


def release_inbox_claims(claims: Iterable[InboxClaim]) -> tuple[Path, ...]:
    """Best-effort release of sources that processing did not consume."""

    unreleased: list[Path] = []
    for claim in claims:
        if not claim.release():
            unreleased.append(claim.claimed_path)
    return tuple(unreleased)


def _ensure_lock_marker(handle: BinaryIO) -> None:
    if os.fstat(handle.fileno()).st_size:
        return
    handle.seek(0)
    handle.write(_LOCK_MARKER)
    handle.flush()
    os.fsync(handle.fileno())


def _write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _try_acquire_os_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_os_lock(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_contention_error(exc: OSError) -> bool:
    return getattr(exc, "winerror", None) in {32, 33} or getattr(exc, "errno", None) in {11, 13}


def _remove_empty_claim_dirs(start: Path, processing_root: Path) -> None:
    current = start
    while current != processing_root.parent:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
