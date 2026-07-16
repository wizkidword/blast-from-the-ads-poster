from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cleanup import CleanupSettings, execute_cleanup, plan_cleanup  # noqa: E402


def touch_old(path: Path, age_days: int, now: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old", encoding="utf-8")
    old_time = now - (age_days * 86400)
    os.utime(path, (old_time, old_time))


class CleanupTests(unittest.TestCase):
    def test_plan_cleanup_targets_only_safe_retention_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = time.time()
            touch_old(root / "temp" / "frames" / "frame.jpg", 1, now)
            touch_old(root / "logs" / "inbox-run-1.json", 120, now)
            touch_old(root / "exports" / "posting-packs" / "old-pack" / "caption.txt", 45, now)
            touch_old(root / "outputs" / "orphan" / "caption.txt", 20, now)
            active_manifest = root / "outputs" / "active" / "post_manifest.json"
            touch_old(active_manifest, 20, now)
            touch_old(root / "inbox" / "do-not-touch.mp4", 120, now)
            touch_old(root / "!processed" / "do-not-touch.mp4", 120, now)

            plan = plan_cleanup(root, CleanupSettings(), now=now)
            targets = {item.path.relative_to(root).as_posix() for item in plan.items}

            self.assertIn("temp/frames/frame.jpg", targets)
            self.assertIn("logs/inbox-run-1.json", targets)
            self.assertIn("exports/posting-packs/old-pack", targets)
            self.assertIn("outputs/orphan", targets)
            self.assertNotIn("outputs/active", targets)
            self.assertNotIn("inbox/do-not-touch.mp4", targets)
            self.assertNotIn("!processed/do-not-touch.mp4", targets)

    def test_execute_cleanup_deletes_planned_items(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = time.time()
            old_log = root / "logs" / "inbox-run-1.json"
            touch_old(old_log, 120, now)

            result = execute_cleanup(plan_cleanup(root, CleanupSettings(), now=now))

            self.assertEqual(result.deleted_count, 1)
            self.assertFalse(old_log.exists())


if __name__ == "__main__":
    unittest.main()
