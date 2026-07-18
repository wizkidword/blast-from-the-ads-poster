from __future__ import annotations

import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app_context import build_app_context  # noqa: E402
from cleanup import CleanupItem, CleanupPlan, execute_cleanup  # noqa: E402
from process_inbox_social import run_inbox_processing  # noqa: E402
from requeue import requeue_output_workspace  # noqa: E402
from workspace_lock import (  # noqa: E402
    CancellationToken,
    OperationCancelled,
    WorkspaceBusyError,
    WorkspaceLock,
    WorkspaceLockError,
    claim_inbox_files,
    read_lock_metadata,
)
from cancellable_subprocess import run_command  # noqa: E402


def _hold_workspace_lock(workspace_text: str, ready, release) -> None:
    with WorkspaceLock(Path(workspace_text), "child processing", run_id="child-run"):
        ready.set()
        release.wait(10)


def _claim_source(inbox_text: str, run_id: str, start, results) -> None:
    start.wait(10)
    try:
        with WorkspaceLock(Path(inbox_text).parent, "inbox processing", run_id=run_id):
            claim_inbox_files(Path(inbox_text), [Path(inbox_text) / "same-source.mp4"], run_id)
    except WorkspaceLockError as exc:
        results.put(("rejected", str(exc)))
    else:
        results.put(("claimed", run_id))


class WorkspaceLockTests(unittest.TestCase):
    def test_second_process_is_refused_and_metadata_identifies_active_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            release = context.Event()
            process = context.Process(target=_hold_workspace_lock, args=(str(root), ready, release))
            process.start()
            try:
                self.assertTrue(ready.wait(10), "child process did not acquire the workspace lock")
                with self.assertRaises(WorkspaceBusyError) as raised:
                    WorkspaceLock(root, "parent cleanup").acquire()
                self.assertIn("child processing", str(raised.exception))
                self.assertEqual(raised.exception.metadata.get("run_id"), "child-run")
            finally:
                release.set()
                process.join(10)
                if process.is_alive():
                    process.terminate()
            self.assertEqual(process.exitcode, 0)
            with WorkspaceLock(root, "parent cleanup"):
                pass

    def test_stale_metadata_is_not_treated_as_an_active_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.mkdir(exist_ok=True)
            lock_path = root / ".workspace.lock"
            (root / ".workspace.lock.json").write_text(
                '{"operation":"old crashed run","pid":99999,"run_id":"stale"}',
                encoding="utf-8",
            )

            with WorkspaceLock(root, "fresh cleanup", run_id="fresh-run"):
                metadata = read_lock_metadata(lock_path)
                self.assertEqual(metadata["operation"], "fresh cleanup")
                self.assertEqual(metadata["run_id"], "fresh-run")

    def test_two_processes_can_claim_a_source_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "same-source.mp4").write_bytes(b"media")
            context = multiprocessing.get_context("spawn")
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(target=_claim_source, args=(str(inbox), f"run-{index}", start, results))
                for index in range(2)
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(10)
                if process.is_alive():
                    process.terminate()
            self.assertEqual([process.exitcode for process in processes], [0, 0])
            outcomes = [results.get(timeout=2)[0] for _ in processes]
            self.assertEqual(outcomes.count("claimed"), 1)
            self.assertEqual(outcomes.count("rejected"), 1)
            self.assertFalse((inbox / "same-source.mp4").exists())
            self.assertEqual(len(list((inbox / ".processing").rglob("same-source.mp4"))), 1)

    def test_cleanup_and_requeue_are_refused_while_processing_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            processed = root / "!processed"
            outputs = root / "outputs"
            captions = root / "captions"
            for directory in (inbox, processed, outputs, captions):
                directory.mkdir()
            stale_log = root / "logs" / "inbox-run-old.json"
            stale_log.parent.mkdir()
            stale_log.write_text("{}", encoding="utf-8")
            cleanup_plan = CleanupPlan(root, (CleanupItem(stale_log, "old run log"),))

            with WorkspaceLock(root, "inbox processing", run_id="active-run"):
                with self.assertRaises(WorkspaceBusyError):
                    execute_cleanup(cleanup_plan)
                with self.assertRaises(WorkspaceBusyError):
                    requeue_output_workspace(outputs / "missing", inbox, processed, root, captions)

            self.assertTrue(stale_log.exists())

    def test_cli_processing_reports_the_active_operation_when_another_run_holds_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = build_app_context(root)
            context.inbox_dir.mkdir(parents=True)
            (context.inbox_dir / "clip.mp4").write_bytes(b"media")

            with (
                WorkspaceLock(root, "desktop processing", run_id="desktop-run"),
                patch("process_inbox_social.load_env", return_value=None),
                patch("process_inbox_social.get_openai_api_key", return_value="test-key"),
            ):
                summary = run_inbox_processing(context=context)

            self.assertEqual(summary[0]["error"], "workspace_busy")
            self.assertEqual(summary[0]["active_operation"], "desktop processing")
            self.assertEqual(summary[0]["active_run_id"], "desktop-run")

    def test_cancellation_releases_claimed_source_at_the_next_safe_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = build_app_context(root)
            source = context.inbox_dir / "long-task.mp4"
            context.inbox_dir.mkdir(parents=True)
            source.write_bytes(b"media")
            token = CancellationToken()

            def cancel_during_mocked_task(_path: Path, *, cancellation_token=None, **_kwargs) -> dict:
                self.assertIs(cancellation_token, token)
                token.request()
                cancellation_token.raise_if_requested()
                raise AssertionError("Cancellation should interrupt the mocked task")

            with (
                patch("process_inbox_social.load_env", return_value=None),
                patch("process_inbox_social.get_openai_api_key", return_value="test-key"),
                patch("process_inbox_social.process_video_file", side_effect=cancel_during_mocked_task),
            ):
                summary = run_inbox_processing(context=context, cancellation_token=token)

            self.assertEqual(summary[0]["status"], "cancelled")
            self.assertTrue(source.exists())
            self.assertFalse((context.inbox_dir / ".processing").exists())

    def test_cancellable_subprocess_stops_a_mocked_long_media_task(self) -> None:
        class LongRunningProcess:
            def __init__(self) -> None:
                self.killed = False
                self.returncode = None

            def poll(self):
                return None

            def kill(self) -> None:
                self.killed = True

            def communicate(self):
                return "", ""

        process = LongRunningProcess()
        checks = 0

        def cancellation_check() -> None:
            nonlocal checks
            checks += 1
            if checks > 1:
                raise OperationCancelled("stop mocked media task")

        with patch("cancellable_subprocess.subprocess.Popen", return_value=process):
            with self.assertRaises(OperationCancelled):
                run_command(["ffmpeg", "-version"], timeout=60, cancellation_check=cancellation_check)

        self.assertTrue(process.killed)


if __name__ == "__main__":
    unittest.main()
