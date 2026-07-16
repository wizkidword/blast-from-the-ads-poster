from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import blast_workflow  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
