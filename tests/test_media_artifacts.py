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

import media_artifacts  # noqa: E402
from media_processing import MediaProcessingTimeout  # noqa: E402


class MediaArtifactsTests(unittest.TestCase):
    def test_proportional_timestamps_cover_later_video_sections(self) -> None:
        timestamps = media_artifacts.proportional_frame_timestamps(180.0, 8)

        self.assertLessEqual(len(timestamps), 8)
        self.assertGreater(timestamps[-1], 100)
        self.assertEqual(timestamps, sorted(timestamps))

    def test_identical_frame_bytes_are_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "video.mp4"
            video.write_bytes(b"video")

            def identical_frames(command, **_kwargs):
                Path(command[-1]).write_bytes(b"same-frame")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(media_artifacts, "run_command", side_effect=identical_frames):
                frames = media_artifacts.extract_video_frames(video, root / "temp", [1, 2])

            self.assertEqual(len(frames), 1)

    def test_frame_extraction_uses_an_isolated_generated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "Apostrophe's and unicode \u6d4b\u8bd5.mp4"
            video.write_bytes(b"video")

            def fake_run(command, **_kwargs):
                frame_path = Path(command[-1])
                frame_path.write_bytes(frame_path.name.encode("utf-8"))
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(media_artifacts, "run_command", side_effect=fake_run):
                first = media_artifacts.extract_video_frames(video, root / "temp", [1, 2])
                second = media_artifacts.extract_video_frames(video, root / "temp", [1, 2])

            self.assertEqual([path.name for path in first], ["frame-001.jpg", "frame-002.jpg"])
            self.assertNotEqual(first[0].parent, second[0].parent)
            self.assertNotIn(video.stem, str(first[0]))
            media_artifacts.cleanup_temp_files([*first, *second], root / "temp")
            self.assertFalse(first[0].parent.exists())
            self.assertFalse(second[0].parent.exists())

    def test_frame_timeout_is_explicit_and_cleans_its_run_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            with patch.object(
                media_artifacts,
                "run_command",
                side_effect=subprocess.TimeoutExpired(["ffmpeg"], 120),
            ):
                with self.assertRaisesRegex(MediaProcessingTimeout, "timed out"):
                    media_artifacts.extract_video_frames(video, root / "temp")

            frame_root = root / "temp" / "frames"
            self.assertFalse(any(frame_root.iterdir()) if frame_root.exists() else False)


if __name__ == "__main__":
    unittest.main()
