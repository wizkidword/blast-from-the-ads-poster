from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_status import build_status_snapshot, count_files, count_output_posts, format_status_line  # noqa: E402


class DesktopStatusTests(unittest.TestCase):
    def test_count_files_can_ignore_gitkeep(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / ".gitkeep").write_text("", encoding="utf-8")
            (folder / "caption.txt").write_text("copy", encoding="utf-8")
            (folder / "nested").mkdir()

            self.assertEqual(count_files(folder), 2)
            self.assertEqual(count_files(folder, ignore_gitkeep=True), 1)

    def test_count_output_posts_only_counts_manifest_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = Path(temp_dir)
            (outputs / "post-one").mkdir()
            (outputs / "post-one" / "post_manifest.json").write_text("{}", encoding="utf-8")
            (outputs / "orphan").mkdir()
            (outputs / "loose.txt").write_text("", encoding="utf-8")

            self.assertEqual(count_output_posts(outputs), 1)

    def test_build_status_snapshot_and_format_status_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            captions = root / "captions"
            processed = root / "!processed"
            outputs = root / "outputs"
            for directory in (inbox, captions, processed, outputs):
                directory.mkdir()
            (inbox / "ad.mp4").write_bytes(b"video")
            (captions / ".gitkeep").write_text("", encoding="utf-8")
            (captions / "ad.txt").write_text("copy", encoding="utf-8")
            (processed / "ad.mp4").write_bytes(b"processed")
            (outputs / "post").mkdir()
            (outputs / "post" / "post_manifest.json").write_text("{}", encoding="utf-8")

            snapshot = build_status_snapshot(inbox, captions, processed, outputs)

            self.assertEqual(snapshot.inbox_count, 1)
            self.assertEqual(snapshot.caption_count, 1)
            self.assertEqual(snapshot.processed_count, 1)
            self.assertEqual(snapshot.output_count, 1)
            self.assertEqual(
                format_status_line(snapshot),
                "Inbox: 1 file(s)    Captions: 1    Processed: 1    Outputs: 1 post(s)",
            )


if __name__ == "__main__":
    unittest.main()
