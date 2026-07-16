from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from social_batch_app import collect_requeue_plan  # noqa: E402


class SocialBatchAppTests(unittest.TestCase):
    def test_collect_requeue_plan_prefers_processed_files_over_shadow_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs_dir = root / "outputs"
            processed_dir = root / "!processed"
            workspace = outputs_dir / "video-123"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            processed_dir.mkdir()

            (workspace / "post_manifest.json").write_text("{}", encoding="utf-8")
            (media_dir / "clip.mp4").write_bytes(b"shadow")
            (media_dir / "lost-only.mp4").write_bytes(b"shadow-only")
            (processed_dir / "clip.mp4").write_bytes(b"primary")

            plan = collect_requeue_plan(outputs_dir, processed_dir)

            self.assertEqual([path.name for path in plan.processed_files], ["clip.mp4"])
            self.assertEqual([path.name for path in plan.output_media_files], ["lost-only.mp4"])
            self.assertEqual(sorted(path.name for path in plan.all_files), ["clip.mp4", "lost-only.mp4"])


if __name__ == "__main__":
    unittest.main()
