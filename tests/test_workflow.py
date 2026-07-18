from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import blast_workflow  # noqa: E402
from app_context import build_app_context, prepare_app_context  # noqa: E402


class WorkflowTests(unittest.TestCase):
    def test_configure_standard_streams_replaces_unencodable_console_chars(self) -> None:
        class FakeStream:
            def __init__(self) -> None:
                self.reconfigure_kwargs = None

            def reconfigure(self, **kwargs) -> None:
                self.reconfigure_kwargs = kwargs

        stdout = FakeStream()
        stderr = FakeStream()

        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            blast_workflow.configure_standard_streams()

        self.assertEqual(stdout.reconfigure_kwargs, {"errors": "replace"})
        self.assertEqual(stderr.reconfigure_kwargs, {"errors": "replace"})

    def test_inbox_command_returns_nonzero_when_processing_summary_has_failures(self) -> None:
        with (
            patch.object(sys, "argv", ["workflow.py", "inbox"]),
            patch.object(blast_workflow, "run_inbox_processing", return_value=[{"status": "failed"}]),
        ):
            self.assertEqual(blast_workflow.main(), 1)

    def test_retry_command_uses_the_shared_current_ledger_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = prepare_app_context(build_app_context(Path(temp_dir)))
            retry = context.inbox_dir / "retry.mp4"
            retry.write_bytes(b"video")
            log_path = context.logs_dir / "inbox-run-current.json"
            log_path.write_text(
                __import__("json").dumps(
                    {
                        "schema_version": 3,
                        "run": {
                            "run_id": "current",
                            "app_version": "test",
                            "command": "inbox",
                            "started_at": None,
                            "ended_at": None,
                            "dry_run": False,
                            "targeted": True,
                        },
                        "records": [{"type": "video", "file": "retry.mp4", "status": "failed"}],
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(sys, "argv", ["workflow.py", "retry", "--run", log_path.name]),
                patch.object(blast_workflow, "build_app_context", return_value=context),
                patch.object(blast_workflow, "run_inbox_processing", return_value=[]) as run_inbox,
            ):
                self.assertEqual(blast_workflow.main(), 0)

            self.assertEqual(run_inbox.call_args.kwargs["target_files"], [retry])
            self.assertEqual(run_inbox.call_args.kwargs["context"], context)


if __name__ == "__main__":
    unittest.main()
