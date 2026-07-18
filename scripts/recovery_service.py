"""One safe retry planner shared by all run-ledger recovery surfaces."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TypeVar

try:
    from media_rules import is_supported_media_file, is_video_file
except ImportError:
    from scripts.media_rules import is_supported_media_file, is_video_file

try:
    from run_ledger import NormalizedRunRecord, load_normalized_run_ledger
except ImportError:
    from scripts.run_ledger import NormalizedRunRecord, load_normalized_run_ledger

try:
    from atomic_io import PersistenceError
except ImportError:
    from scripts.atomic_io import PersistenceError

try:
    from safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, require_plain_filename, resolve_existing_under, resolve_output_under


RETRY_MODES = {"all", "videos", "images"}
T = TypeVar("T")


@dataclass(frozen=True)
class RetryCandidate:
    filename: str
    path: Path
    media_type: str
    run_ids: tuple[str, ...]
    error: str
    available: bool
    skip_reason: str | None = None


@dataclass(frozen=True)
class RetryPlan:
    candidates: tuple[RetryCandidate, ...]
    errors: tuple[str, ...] = ()

    @property
    def retry_files(self) -> tuple[Path, ...]:
        return tuple(candidate.path for candidate in self.candidates if candidate.available and candidate.skip_reason is None)

    @property
    def missing_files(self) -> tuple[str, ...]:
        return tuple(candidate.filename for candidate in self.candidates if not candidate.available)

    @property
    def skipped_files(self) -> tuple[str, ...]:
        return tuple(candidate.filename for candidate in self.candidates if candidate.skip_reason is not None)


def build_retry_plan(
    log_paths: Iterable[Path],
    inbox_dir: Path,
    *,
    outputs_dir: Path | None = None,
    mode: str = "all",
) -> RetryPlan:
    """Plan retry targets without moving, replacing, or otherwise changing media."""

    if mode not in RETRY_MODES:
        raise ValueError(f"Unsupported retry mode: {mode}")
    inbox_dir = resolve_existing_under(inbox_dir, inbox_dir)
    outputs_dir = _safe_outputs_dir(outputs_dir or (inbox_dir.parent / "outputs"))
    candidates: dict[str, RetryCandidate] = {}
    errors: list[str] = []
    for raw_log_path in log_paths:
        try:
            log_path = resolve_existing_under(Path(raw_log_path).parent, raw_log_path)
            ledger = load_normalized_run_ledger(log_path)
        except (OSError, ValueError, UnsafePathError, PersistenceError) as exc:
            errors.append(f"Quarantined from retry: {Path(raw_log_path).name}: {exc}")
            continue

        for record in ledger.records:
            if record.status != "failed":
                continue
            for raw_filename in record.media_names:
                candidate = _candidate_from_record(
                    raw_filename,
                    record,
                    ledger.run_id,
                    inbox_dir,
                    outputs_dir,
                )
                if candidate is None:
                    errors.append(f"Quarantined from retry: {log_path.name}: unsafe filename {raw_filename!r}")
                    continue
                if mode != "all" and candidate.media_type != mode.removesuffix("s"):
                    continue
                key = candidate.filename.lower()
                existing = candidates.get(key)
                if existing is None:
                    candidates[key] = candidate
                else:
                    candidates[key] = _merge_candidates(existing, candidate)
    return RetryPlan(candidates=tuple(candidates.values()), errors=tuple(errors))


def execute_retry_plan(plan: RetryPlan, executor: Callable[[list[Path]], T]) -> T | None:
    """Use one target list for every caller; the caller supplies its UI/CLI executor."""

    retry_files = list(plan.retry_files)
    return executor(retry_files) if retry_files else None


def filter_retry_plan(plan: RetryPlan, mode: str = "all") -> RetryPlan:
    if mode not in RETRY_MODES:
        raise ValueError(f"Unsupported retry mode: {mode}")
    if mode == "all":
        return plan
    media_type = mode.removesuffix("s")
    return RetryPlan(
        candidates=tuple(candidate for candidate in plan.candidates if candidate.media_type == media_type),
        errors=plan.errors,
    )


def _candidate_from_record(
    raw_filename: str,
    record: NormalizedRunRecord,
    run_id: str,
    inbox_dir: Path,
    outputs_dir: Path | None,
) -> RetryCandidate | None:
    try:
        filename = require_plain_filename(raw_filename)
        path = resolve_output_under(inbox_dir, filename)
    except UnsafePathError:
        return None

    media_type = "video" if is_video_file(path) else "image"
    available = path.exists() and resolve_existing_under(inbox_dir, path).is_file() and is_supported_media_file(path)
    skip_reason = _committed_output_reason(record, outputs_dir)
    return RetryCandidate(
        filename=filename,
        path=path,
        media_type=media_type,
        run_ids=(run_id,),
        error=record.error_message or "failed",
        available=available,
        skip_reason=skip_reason,
    )


def _merge_candidates(first: RetryCandidate, second: RetryCandidate) -> RetryCandidate:
    run_ids = tuple(dict.fromkeys([*first.run_ids, *second.run_ids]))
    errors = tuple(dict.fromkeys([first.error, second.error]))
    return RetryCandidate(
        filename=first.filename,
        path=first.path,
        media_type=first.media_type,
        run_ids=run_ids,
        error="; ".join(errors),
        available=first.available or second.available,
        skip_reason=first.skip_reason or second.skip_reason,
    )


def _safe_outputs_dir(outputs_dir: Path | None) -> Path | None:
    if outputs_dir is None or not Path(outputs_dir).exists():
        return None
    return resolve_existing_under(outputs_dir, outputs_dir)


def _committed_output_reason(record: NormalizedRunRecord, outputs_dir: Path | None) -> str | None:
    if outputs_dir is None or record.output_dir is None:
        return None
    try:
        raw_workspace = record.output_dir
        if not raw_workspace.is_absolute() and raw_workspace.parts[:1] == ("outputs",):
            raw_workspace = Path(*raw_workspace.parts[1:])
        workspace = resolve_output_under(outputs_dir, raw_workspace)
    except UnsafePathError:
        return "Ledger output path is unsafe; not retrying"
    if workspace.is_dir() and (workspace / "post_manifest.json").is_file():
        return "Final workspace is already committed; not retrying"
    return None
