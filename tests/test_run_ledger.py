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

from app_metadata import APP_VERSION  # noqa: E402
from run_ledger import normalize_run_log, write_run_ledger  # noqa: E402


class RunLedgerTests(unittest.TestCase):
    def test_write_run_ledger_creates_schema_wrapped_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            path = write_run_ledger(
                logs_dir,
                records=[
                    {"type": "video", "file": "clip.mp4", "status": "processed", "analysis_source": "gemini_vision"},
                    {"type": "video", "file": "bad.mp4", "status": "failed", "error": "boom"},
                ],
                command="inbox",
                dry_run=False,
                targeted=True,
                run_id="12345",
            )

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["run"]["run_id"], "12345")
            self.assertEqual(payload["run"]["app_version"], APP_VERSION)
            self.assertTrue(payload["run"]["targeted"])
            self.assertEqual(payload["summary"]["processed"], 1)
            self.assertEqual(payload["summary"]["failed"], 1)
            self.assertEqual(len(payload["records"]), 2)

    def test_normalize_run_log_supports_legacy_array_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "inbox-run-99.json"
            path.write_text(json.dumps([{"type": "video", "file": "clip.mp4", "status": "processed"}]), encoding="utf-8")

            normalized = normalize_run_log(path)

            self.assertEqual(normalized["run"]["run_id"], "99")
            self.assertEqual(normalized["summary"]["processed"], 1)
            self.assertEqual(normalized["records"][0]["file"], "clip.mp4")


if __name__ == "__main__":
    unittest.main()
