from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import media_processing  # noqa: E402


class MediaProcessingTests(unittest.TestCase):
    def test_convert_video_to_vertical_uses_full_1080x1920_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.mp4"
            output = root / "output.mp4"
            source.write_bytes(b"video")
            captured: dict[str, object] = {}

            def fake_run(cmd, capture_output, text, timeout, check):
                captured["cmd"] = cmd
                output.write_bytes(b"converted-video")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                patch.object(media_processing.subprocess, "run", side_effect=fake_run),
                patch.object(media_processing, "get_media_dimensions", return_value=(1080, 1920)),
            ):
                created = media_processing.convert_video_to_vertical(source, output)

            self.assertTrue(created)
            cmd = captured["cmd"]
            filter_arg = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=1080:1920:force_original_aspect_ratio=decrease", filter_arg)
            self.assertIn("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black", filter_arg)

    def test_get_media_dimensions_reads_first_width_height_pair_from_noisy_ffprobe_output(self) -> None:
        output_path = Path("carousel-video.mp4")

        def fake_run(cmd, capture_output, text, timeout, check):
            return subprocess.CompletedProcess(cmd, 0, "1080x1350x\n1080x1350\n", "")

        with patch.object(media_processing.subprocess, "run", side_effect=fake_run):
            dimensions = media_processing.get_media_dimensions(output_path)

        self.assertEqual(dimensions, (1080, 1350))

    def test_create_carousel_video_from_images_uses_ffmpeg_concat_slideshow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first image.jpg"
            second = root / "second image.jpg"
            output = root / "carousel-video.mp4"
            first.write_bytes(b"image-one")
            second.write_bytes(b"image-two")
            captured: dict[str, object] = {}

            def fake_run(cmd, capture_output, text, timeout, check):
                captured["cmd"] = cmd
                concat_path = Path(cmd[cmd.index("-i") + 1])
                captured["concat_text"] = concat_path.read_text(encoding="utf-8")
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                patch.object(media_processing.subprocess, "run", side_effect=fake_run),
                patch.object(media_processing, "get_media_dimensions", return_value=(1080, 1920)),
            ):
                created = media_processing.create_carousel_video_from_images([first, second], output)

            self.assertTrue(created)
            self.assertEqual(output.read_bytes(), b"video")
            cmd = captured["cmd"]
            self.assertIn("-f", cmd)
            self.assertIn("concat", cmd)
            self.assertIn("-safe", cmd)
            filter_arg = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=1080:1920:force_original_aspect_ratio=decrease", filter_arg)
            self.assertIn("pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black", filter_arg)
            self.assertEqual(cmd[-1], str(output))
            concat_text = str(captured["concat_text"])
            self.assertIn("duration 2.5", concat_text)
            self.assertIn(str(first), concat_text)
            self.assertIn(str(second), concat_text)


if __name__ == "__main__":
    unittest.main()
