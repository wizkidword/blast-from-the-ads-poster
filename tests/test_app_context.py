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

import process_inbox_social as processor  # noqa: E402
from app_context import AppContextError, build_app_context, prepare_app_context  # noqa: E402
from settings_store import AppSettings, save_settings  # noqa: E402


class AppContextTests(unittest.TestCase):
    def test_prepare_creates_a_valid_distinct_directory_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = build_app_context(
                root,
                settings=AppSettings(captions_dir="runtime/captions", processed_dir="runtime/processed"),
            )

            prepared = prepare_app_context(context)

            self.assertEqual(prepared, context)
            self.assertTrue(context.inbox_dir.is_dir())
            self.assertTrue(context.captions_dir.is_dir())
            self.assertTrue(context.processed_dir.is_dir())
            self.assertTrue(context.outputs_dir.is_dir())
            with self.assertRaises(AttributeError):
                context.inbox_dir = root / "other"  # type: ignore[misc]

    def test_prepare_rejects_overlapping_nested_and_file_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            same = build_app_context(root, settings=AppSettings(captions_dir="shared", processed_dir="shared"))
            with self.assertRaisesRegex(AppContextError, "same directory"):
                prepare_app_context(same)

            nested = build_app_context(root, settings=AppSettings(captions_dir="runtime", processed_dir="runtime/processed"))
            with self.assertRaisesRegex(AppContextError, "nested"):
                prepare_app_context(nested)

            file_path = root / "not-a-directory"
            file_path.write_text("not a folder", encoding="utf-8")
            file_context = build_app_context(root, settings=AppSettings(captions_dir=str(file_path)))
            with self.assertRaisesRegex(AppContextError, "not a file|not be a directory"):
                prepare_app_context(file_context)

    def test_prepare_reports_non_writable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_app_context(Path(temp_dir))
            with patch("app_context.tempfile.mkstemp", side_effect=PermissionError("access denied")):
                with self.assertRaisesRegex(AppContextError, "not writable"):
                    prepare_app_context(context)

    def test_next_processing_run_uses_the_context_built_from_new_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            save_settings(
                root / "settings.json",
                AppSettings(captions_dir="new/captions", processed_dir="new/processed"),
            )
            context = build_app_context(root)
            context.inbox_dir.mkdir(parents=True)
            source = context.inbox_dir / "ad.mp4"
            source.write_bytes(b"video")
            captured_contexts = []

            def fake_process(path: Path, dry_run: bool = False, *, context):
                captured_contexts.append(context)
                return {"type": "video", "file": path.name, "status": "processed"}

            with (
                patch.object(processor, "load_env", return_value=None),
                patch.object(processor, "get_openai_api_key", return_value="test-key"),
                patch.object(processor, "process_video_file", side_effect=fake_process),
            ):
                summary = processor.run_inbox_processing(context=context)

            self.assertEqual(summary[0]["status"], "processed")
            self.assertEqual(captured_contexts, [context])
            self.assertTrue(context.captions_dir.is_dir())
            self.assertTrue(context.processed_dir.is_dir())
            self.assertEqual(len(list(context.logs_dir.glob("inbox-run-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
