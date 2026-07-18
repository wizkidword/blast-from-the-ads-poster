from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from requeue import collect_failed_run_retry_plan, collect_requeue_plan, requeue_output_workspace  # noqa: E402
from safe_paths import UnsafePathError  # noqa: E402


class RequeueTests(unittest.TestCase):
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

    def test_collect_requeue_plan_excludes_generated_carousel_video_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs_dir = root / "outputs"
            processed_dir = root / "!processed"
            workspace = outputs_dir / "carousel-123"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            processed_dir.mkdir()

            manifest = {
                "media_files": [
                    {"filename": "scan.jpg", "role": "carousel_item"},
                    {"filename": "carousel-video.mp4", "role": "carousel_video"},
                ]
            }
            (workspace / "post_manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
            (processed_dir / "scan.jpg").write_bytes(b"image")
            (processed_dir / "carousel-video.mp4").write_bytes(b"generated-video")
            (media_dir / "carousel-video.mp4").write_bytes(b"shadow-video")

            plan = collect_requeue_plan(outputs_dir, processed_dir)

            self.assertEqual([path.name for path in plan.processed_files], ["scan.jpg"])
            self.assertEqual(plan.output_media_files, [])
            self.assertEqual([path.name for path in plan.all_files], ["scan.jpg"])

    def test_requeue_output_workspace_prefers_primary_processed_file_and_removes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            processed = root / "!processed"
            captions = root / "captions"
            workspace = root / "outputs" / "video-123"
            media = workspace / "media"
            for directory in (inbox, processed, captions, media):
                directory.mkdir(parents=True)

            manifest = {
                "paths": {"legacy_caption_path": "captions/clip.txt"},
                "media_files": [{"filename": "clip.mp4"}],
            }
            (workspace / "post_manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
            (workspace / "caption.txt").write_text("caption", encoding="utf-8")
            (media / "clip.mp4").write_bytes(b"shadow")
            (processed / "clip.mp4").write_bytes(b"primary")
            (captions / "clip.txt").write_text("legacy", encoding="utf-8")

            result = requeue_output_workspace(workspace, inbox, processed, root)

            self.assertEqual(result.moved_files, (inbox.resolve() / "clip.mp4",))
            self.assertEqual((inbox / "clip.mp4").read_bytes(), b"primary")
            self.assertFalse((processed / "clip.mp4").exists())
            self.assertFalse(workspace.exists())
            self.assertFalse((captions / "clip.txt").exists())

    def test_requeue_output_workspace_deletes_generated_carousel_video_instead_of_moving_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            processed = root / "!processed"
            workspace = root / "outputs" / "carousel-123"
            media = workspace / "media"
            for directory in (inbox, processed, media):
                directory.mkdir(parents=True)

            manifest = {
                "media_files": [
                    {"filename": "scan.jpg", "role": "carousel_item"},
                    {"filename": "carousel-video.mp4", "role": "carousel_video"},
                ],
            }
            (workspace / "post_manifest.json").write_text(__import__("json").dumps(manifest), encoding="utf-8")
            (media / "scan.jpg").write_bytes(b"shadow-image")
            (media / "carousel-video.mp4").write_bytes(b"shadow-video")
            (processed / "scan.jpg").write_bytes(b"primary-image")
            (processed / "carousel-video.mp4").write_bytes(b"generated-video")

            result = requeue_output_workspace(workspace, inbox, processed, root)

            self.assertEqual(result.moved_files, (inbox.resolve() / "scan.jpg",))
            self.assertEqual((inbox / "scan.jpg").read_bytes(), b"primary-image")
            self.assertFalse((inbox / "carousel-video.mp4").exists())
            self.assertFalse((processed / "carousel-video.mp4").exists())
            self.assertFalse(workspace.exists())

    def test_collect_failed_run_retry_plan_uses_only_failed_files_that_remain_in_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            logs = root / "logs"
            inbox.mkdir()
            logs.mkdir()
            (inbox / "failed.mp4").write_bytes(b"video")
            log_path = logs / "inbox-run-123.json"
            log_path.write_text(
                __import__("json").dumps(
                    [
                        {"type": "video", "file": "failed.mp4", "status": "failed"},
                        {"type": "video", "file": "gone.mp4", "status": "failed"},
                        {"type": "video", "file": "done.mp4", "status": "processed"},
                    ]
                ),
                encoding="utf-8",
            )

            result = collect_failed_run_retry_plan(log_path, inbox)

            self.assertEqual(result.retry_files, (inbox.resolve() / "failed.mp4",))
            self.assertEqual(result.missing_files, ("gone.mp4",))

    def test_requeue_refuses_unsafe_manifest_filename_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            processed = root / "!processed"
            captions = root / "captions"
            workspace = root / "outputs" / "video-123"
            media = workspace / "media"
            for directory in (inbox, processed, captions, media):
                directory.mkdir(parents=True)
            (processed / "clip.mp4").write_bytes(b"primary")
            (workspace / "post_manifest.json").write_text(
                __import__("json").dumps({"media_files": [{"filename": "../outside.mp4"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(UnsafePathError):
                requeue_output_workspace(workspace, inbox, processed, root, captions)

            self.assertTrue(workspace.exists())
            self.assertTrue((processed / "clip.mp4").exists())
            self.assertFalse((inbox / "clip.mp4").exists())

    def test_failed_run_retry_refuses_unsafe_ledger_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            logs = root / "logs"
            inbox.mkdir()
            logs.mkdir()
            log_path = logs / "inbox-run-123.json"
            log_path.write_text(__import__("json").dumps([{"file": "../outside.mp4", "status": "failed"}]), encoding="utf-8")

            with self.assertRaises(UnsafePathError):
                collect_failed_run_retry_plan(log_path, inbox)

            self.assertFalse((root / "outside.mp4").exists())


if __name__ == "__main__":
    unittest.main()
