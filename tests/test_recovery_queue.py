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


class RecoveryQueueTests(unittest.TestCase):
    def test_build_recovery_queue_marks_available_and_stale_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            logs = root / "logs"
            inbox.mkdir()
            logs.mkdir()
            (inbox / "still-here.mp4").write_bytes(b"video")
            (logs / "inbox-run-1.json").write_text(
                json.dumps(
                    [
                        {"type": "video", "file": "still-here.mp4", "status": "failed", "error": "boom"},
                        {"type": "image_carousel", "files": ["missing.jpg"], "status": "failed", "error": "gone"},
                    ]
                ),
                encoding="utf-8",
            )

            queue = build_recovery_queue(logs, inbox)

            self.assertEqual([item.filename for item in queue.items], ["still-here.mp4", "missing.jpg"])
            self.assertTrue(queue.items[0].available)
            self.assertFalse(queue.items[1].available)
            self.assertEqual(queue.available_count, 1)
            self.assertEqual(queue.stale_count, 1)

    def test_plan_retry_targets_filters_by_media_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            logs = root / "logs"
            inbox.mkdir()
            logs.mkdir()
            (inbox / "clip.mp4").write_bytes(b"video")
            (inbox / "ad.jpg").write_bytes(b"image")
            (logs / "inbox-run-1.json").write_text(
                json.dumps(
                    [
                        {"type": "video", "file": "clip.mp4", "status": "failed"},
                        {"type": "image_carousel", "files": ["ad.jpg"], "status": "failed"},
                    ]
                ),
                encoding="utf-8",
            )

            queue = build_recovery_queue(logs, inbox)

            self.assertEqual([path.name for path in plan_retry_targets(queue, mode="videos")], ["clip.mp4"])
            self.assertEqual([path.name for path in plan_retry_targets(queue, mode="images")], ["ad.jpg"])
            self.assertEqual([path.name for path in plan_retry_targets(queue, mode="all")], ["clip.mp4", "ad.jpg"])


if __name__ == "__main__":
    unittest.main()
