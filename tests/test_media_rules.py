from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from media_rules import (  # noqa: E402
    IMAGE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    VIDEO_EXTENSIONS,
    is_image_file,
    is_supported_media_file,
    is_video_file,
    split_media_files,
    unique_destination,
)


class MediaRulesTests(unittest.TestCase):
    def test_supported_extensions_are_the_union_of_images_and_videos(self) -> None:
        self.assertEqual(SUPPORTED_EXTENSIONS, IMAGE_EXTENSIONS | VIDEO_EXTENSIONS)
        self.assertIn(".jpg", IMAGE_EXTENSIONS)
        self.assertIn(".mp4", VIDEO_EXTENSIONS)

    def test_media_classification_is_case_insensitive(self) -> None:
        self.assertTrue(is_image_file(Path("SCAN.JPG")))
        self.assertTrue(is_video_file(Path("clip.MOV")))
        self.assertTrue(is_supported_media_file(Path("ad.WebP")))
        self.assertFalse(is_supported_media_file(Path("notes.txt")))

    def test_split_media_files_preserves_input_order_within_each_group(self) -> None:
        files = [
            Path("b-video.mp4"),
            Path("a-image.jpg"),
            Path("ignored.txt"),
            Path("c-video.mov"),
            Path("b-image.png"),
        ]

        videos, images = split_media_files(files)

        self.assertEqual([path.name for path in videos], ["b-video.mp4", "c-video.mov"])
        self.assertEqual([path.name for path in images], ["a-image.jpg", "b-image.png"])

    def test_unique_destination_adds_counter_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "clip.mp4").write_bytes(b"one")
            (root / "clip-1.mp4").write_bytes(b"two")

            self.assertEqual(unique_destination(root / "clip.mp4"), root / "clip-2.mp4")


if __name__ == "__main__":
    unittest.main()
