from __future__ import annotations

import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import media_processing  # noqa: E402
from media_processing import MediaProcessingTimeout  # noqa: E402


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
            self.assertIn("file 'frame-000001.jpg'", concat_text)
            self.assertIn("file 'frame-000002.jpg'", concat_text)
            self.assertNotIn(first.name, concat_text)
            self.assertNotIn(second.name, concat_text)

    def test_carousel_concat_never_contains_untrusted_filename_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "normal.jpg"
            second = root / ("quote' unicode \u6d4b\u8bd5 " + ("x" * 120) + ".jpg")
            output = root / "carousel-video.mp4"
            first.write_bytes(b"image-one")
            second.write_bytes(b"image-two")
            captured: dict[str, object] = {}

            def fake_run(command, **_kwargs):
                concat_path = Path(command[command.index("-i") + 1])
                captured["text"] = concat_path.read_text(encoding="utf-8")
                captured["stage"] = concat_path.parent
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch.object(media_processing, "run_command", side_effect=fake_run),
                patch.object(media_processing, "get_media_dimensions", return_value=(1080, 1920)),
            ):
                created = media_processing.create_carousel_video_from_images([first, second], output)

            self.assertTrue(created)
            concat_text = str(captured["text"])
            self.assertNotIn(first.name, concat_text)
            self.assertNotIn(second.name, concat_text)
            self.assertEqual(concat_text.count("file 'frame-"), 3)
            self.assertFalse(Path(captured["stage"]).exists())

    def test_concurrent_carousels_receive_distinct_staging_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "source image.jpg"
            image.write_bytes(b"image")
            stage_paths: list[Path] = []

            def fake_run(command, **_kwargs):
                concat_path = Path(command[command.index("-i") + 1])
                stage_paths.append(concat_path.parent)
                Path(command[-1]).write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            def create(index: int) -> bool:
                return media_processing.create_carousel_video_from_images([image], root / f"carousel-{index}.mp4")

            with (
                patch.object(media_processing, "run_command", side_effect=fake_run),
                patch.object(media_processing, "get_media_dimensions", return_value=(1080, 1920)),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                results = list(executor.map(create, (1, 2)))

            self.assertEqual(results, [True, True])
            self.assertEqual(len(set(stage_paths)), 2)
            self.assertTrue(all(not stage.exists() for stage in stage_paths))

    def test_ffmpeg_timeout_is_reported_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            with patch.object(
                media_processing,
                "run_command",
                side_effect=subprocess.TimeoutExpired(["ffmpeg"], 600),
            ):
                with self.assertRaisesRegex(MediaProcessingTimeout, "timed out"):
                    media_processing.convert_video_to_vertical(source, root / "output.mp4")

    def test_success_exit_without_valid_output_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            source.write_bytes(b"image")
            with patch.object(
                media_processing,
                "run_command",
                return_value=subprocess.CompletedProcess(["ffmpeg"], 0, "", ""),
            ):
                created = media_processing.convert_image_to_instagram(source, root / "missing.jpg")

            self.assertFalse(created)


if __name__ == "__main__":
    unittest.main()
