from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_requeue import build_requeue_confirmation, execute_requeue_plan  # noqa: E402
from requeue import collect_requeue_plan  # noqa: E402
from safe_paths import UnsafePathError  # noqa: E402


class DesktopRequeueTests(unittest.TestCase):
    def test_build_requeue_confirmation_summarizes_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            processed = root / "!processed"
            workspace = outputs / "video-123"
            media = workspace / "media"
            media.mkdir(parents=True)
            processed.mkdir()
            (workspace / "post_manifest.json").write_text("{}", encoding="utf-8")
            (media / "clip.mp4").write_bytes(b"shadow")
            (processed / "clip.mp4").write_bytes(b"primary")

            text = build_requeue_confirmation(collect_requeue_plan(outputs, processed))

            self.assertIn("Move 1 file(s)", text)
            self.assertIn("Output workspaces: 1", text)
            self.assertIn("Legacy processed files: 1", text)
            self.assertIn("Videos: 1", text)

    def test_execute_requeue_plan_moves_primary_and_removes_workspace_and_captions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            processed = root / "!processed"
            inbox = root / "inbox"
            captions = root / "captions"
            workspace = outputs / "video-123"
            media = workspace / "media"
            for directory in (media, processed, inbox, captions):
                directory.mkdir(parents=True, exist_ok=True)
            (media / "clip.mp4").write_bytes(b"shadow")
            (processed / "clip.mp4").write_bytes(b"primary")
            (captions / "clip.txt").write_text("old caption", encoding="utf-8")
            (workspace / "caption.txt").write_text("workspace caption", encoding="utf-8")
            (workspace / "post_manifest.json").write_text(
                '{"paths": {"legacy_caption_path": "captions/clip.txt"}}',
                encoding="utf-8",
            )
            plan = collect_requeue_plan(outputs, processed)

            result = execute_requeue_plan(plan, inbox, captions, root)

            self.assertEqual(result.moved_count, 1)
            self.assertEqual(result.removed_captions, 1)
            self.assertEqual(result.removed_workspaces, 1)
            self.assertEqual((inbox / "clip.mp4").read_bytes(), b"primary")
            self.assertFalse(workspace.exists())
            self.assertFalse((captions / "clip.txt").exists())

    def test_execute_requeue_plan_refuses_unsafe_legacy_caption_path_before_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            processed = root / "!processed"
            inbox = root / "inbox"
            captions = root / "captions"
            workspace = outputs / "video-123"
            media = workspace / "media"
            for directory in (media, processed, inbox, captions):
                directory.mkdir(parents=True, exist_ok=True)
            (media / "clip.mp4").write_bytes(b"shadow")
            (processed / "clip.mp4").write_bytes(b"primary")
            (workspace / "post_manifest.json").write_text(
                '{"paths": {"legacy_caption_path": "../outside.txt"}}',
                encoding="utf-8",
            )
            plan = collect_requeue_plan(outputs, processed)

            with self.assertRaises(UnsafePathError):
                execute_requeue_plan(plan, inbox, captions, root, processed)

            self.assertTrue(workspace.exists())
            self.assertTrue((processed / "clip.mp4").exists())
            self.assertFalse((inbox / "clip.mp4").exists())


if __name__ == "__main__":
    unittest.main()
