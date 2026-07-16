from __future__ import annotations

import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_workflow import format_workflow_label, parse_limit_value, run_workflow_action  # noqa: E402


class DesktopWorkflowTests(unittest.TestCase):
    def test_parse_limit_value_accepts_blank_or_positive_integer(self) -> None:
        self.assertIsNone(parse_limit_value(""))
        self.assertIsNone(parse_limit_value("   "))
        self.assertEqual(parse_limit_value("10"), 10)

    def test_parse_limit_value_rejects_invalid_values(self) -> None:
        for raw in ("0", "-1", "two"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_limit_value(raw)

    def test_format_workflow_label_matches_desktop_log_text(self) -> None:
        self.assertEqual(format_workflow_label("setup", None, False, None), "Running: setup")
        self.assertEqual(format_workflow_label("inbox", 5, True, None), "Running: inbox --dry-run --limit 5")
        self.assertEqual(
            format_workflow_label("inbox", None, False, [Path("a.mp4"), Path("b.mp4")]),
            "Running: inbox targeted retry for 2 file(s)",
        )
        self.assertEqual(format_workflow_label("inbox", 3, False, None), "Running: inbox --limit 3")

    def test_run_workflow_action_maps_failures_to_nonzero_exit_code(self) -> None:
        exit_code = run_workflow_action(
            "inbox",
            limit=2,
            dry_run=False,
            target_files=None,
            setup_check_func=lambda: 0,
            run_inbox_processing_func=lambda **_kwargs: [{"status": "failed"}],
            has_failed_results_func=lambda summary: any(item["status"] == "failed" for item in summary),
        )
        self.assertEqual(exit_code, 1)

    def test_run_workflow_action_runs_setup_and_rejects_unknown_action(self) -> None:
        self.assertEqual(
            run_workflow_action(
                "setup",
                limit=None,
                dry_run=False,
                target_files=None,
                setup_check_func=lambda: 0,
                run_inbox_processing_func=lambda **_kwargs: [],
                has_failed_results_func=lambda _summary: False,
            ),
            0,
        )
        output = StringIO()
        with redirect_stdout(output):
            unknown_exit_code = run_workflow_action(
                "nope",
                limit=None,
                dry_run=False,
                target_files=None,
                setup_check_func=lambda: 0,
                run_inbox_processing_func=lambda **_kwargs: [],
                has_failed_results_func=lambda _summary: False,
            )
        self.assertEqual(unknown_exit_code, 1)
        self.assertIn("ERROR: Unknown action 'nope'", output.getvalue())


if __name__ == "__main__":
    unittest.main()
