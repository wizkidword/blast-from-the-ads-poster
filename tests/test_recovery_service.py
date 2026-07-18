from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from recovery_queue import build_recovery_queue, plan_retry_targets  # noqa: E402
from recovery_service import build_retry_plan, execute_retry_plan, filter_retry_plan  # noqa: E402
from requeue import collect_failed_run_retry_plan  # noqa: E402
from run_history import collect_failed_retry_candidates  # noqa: E402
from run_ledger import load_normalized_run_ledger  # noqa: E402


class RecoveryServiceTests(unittest.TestCase):
    def _workspace(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        inbox = root / "inbox"
        logs = root / "logs"
        outputs = root / "outputs"
        for directory in (inbox, logs, outputs):
            directory.mkdir()
        return temporary, inbox, logs, outputs

    def _write_current_log(self, path: Path, records: list[dict]) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "run": {
                        "run_id": path.stem.removeprefix("inbox-run-"),
                        "app_version": "test",
                        "command": "inbox",
                        "started_at": None,
                        "ended_at": None,
                        "dry_run": False,
                        "targeted": False,
                    },
                    "records": records,
                }
            ),
            encoding="utf-8",
        )

    def test_current_ledger_uses_one_plan_for_queue_selected_history_and_cli_executor(self) -> None:
        temporary, inbox, logs, outputs = self._workspace()
        with temporary:
            retry = inbox / "retry.mp4"
            image = inbox / "retry.jpg"
            retry.write_bytes(b"video")
            image.write_bytes(b"image")
            log_path = logs / "inbox-run-current.json"
            self._write_current_log(
                log_path,
                [
                    {"type": "video", "file": "retry.mp4", "status": "failed", "error": "network"},
                    {"type": "video", "file": "retry.mp4", "status": "failed", "error": "duplicate"},
                    {"type": "image_carousel", "files": ["retry.jpg"], "status": "failed", "error": "network"},
                ],
            )

            plan = build_retry_plan([log_path], inbox, outputs_dir=outputs)
            queue = build_recovery_queue(logs, inbox, outputs)
            selected = collect_failed_run_retry_plan(log_path, inbox, outputs)
            history = collect_failed_retry_candidates(log_path, inbox)
            executed: list[Path] = []

            execute_retry_plan(plan, lambda paths: executed.extend(paths))

            self.assertEqual([path.name for path in plan.retry_files], ["retry.mp4", "retry.jpg"])
            self.assertEqual([path.name for path in plan_retry_targets(queue)], ["retry.mp4", "retry.jpg"])
            self.assertEqual(selected.retry_files, plan.retry_files)
            self.assertEqual(history, list(plan.retry_files))
            self.assertEqual(executed, list(plan.retry_files))
            self.assertEqual([path.name for path in filter_retry_plan(plan, "videos").retry_files], ["retry.mp4"])
            self.assertEqual(len(plan.candidates[0].run_ids), 1)

    def test_legacy_array_normalizes_to_the_same_retry_model(self) -> None:
        temporary, inbox, logs, outputs = self._workspace()
        with temporary:
            (inbox / "legacy.mp4").write_bytes(b"video")
            log_path = logs / "inbox-run-legacy.json"
            log_path.write_text(json.dumps([{"type": "video", "file": "legacy.mp4", "status": "failed"}]), encoding="utf-8")

            ledger = load_normalized_run_ledger(log_path)
            plan = build_retry_plan([log_path], inbox, outputs_dir=outputs)

            self.assertEqual(ledger.run_id, "legacy")
            self.assertEqual(ledger.records[0].media_names, ("legacy.mp4",))
            self.assertEqual(plan.retry_files, (inbox.resolve() / "legacy.mp4",))

    def test_bad_or_unknown_ledgers_are_quarantined_from_retry_without_mutation(self) -> None:
        temporary, inbox, logs, outputs = self._workspace()
        with temporary:
            unknown = logs / "inbox-run-unknown.json"
            unknown.write_text(json.dumps({"schema_version": 99, "run": {}, "records": []}), encoding="utf-8")
            damaged = logs / "inbox-run-damaged.json"
            damaged.write_text('{"schema_version": 3', encoding="utf-8")

            plan = build_retry_plan([unknown, damaged], inbox, outputs_dir=outputs)

            self.assertEqual(plan.retry_files, ())
            self.assertEqual(len(plan.errors), 2)
            self.assertTrue(all("Quarantined from retry" in error for error in plan.errors))
            self.assertTrue(unknown.exists())
            self.assertTrue(damaged.exists())

    def test_final_committed_workspace_is_never_retried(self) -> None:
        temporary, inbox, logs, outputs = self._workspace()
        with temporary:
            (inbox / "done.mp4").write_bytes(b"source")
            workspace = outputs / "already-committed"
            workspace.mkdir()
            (workspace / "post_manifest.json").write_text("{}", encoding="utf-8")
            log_path = logs / "inbox-run-committed.json"
            self._write_current_log(
                log_path,
                [
                    {
                        "type": "video",
                        "file": "done.mp4",
                        "status": "failed",
                        "output_dir": "outputs/already-committed",
                    }
                ],
            )

            plan = build_retry_plan([log_path], inbox, outputs_dir=outputs)

            self.assertEqual(plan.retry_files, ())
            self.assertEqual(plan.skipped_files, ("done.mp4",))
            self.assertIn("already committed", plan.candidates[0].skip_reason)


if __name__ == "__main__":
    unittest.main()
