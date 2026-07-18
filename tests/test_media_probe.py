from __future__ import annotations

import json
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

import media_probe  # noqa: E402
from media_probe import MediaLimits, MediaProbeError, MediaValidationError, preflight_media_files, validate_media  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _png_with_dimensions(width: int, height: int) -> bytes:
    return _ONE_PIXEL_PNG[:16] + width.to_bytes(4, "big") + height.to_bytes(4, "big") + _ONE_PIXEL_PNG[24:]


class MediaProbeTests(unittest.TestCase):
    def test_corrupt_supported_extension_is_rejected_before_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "corrupt.jpg"
            path.write_bytes(b"not an image")
            failed_probe = subprocess.CompletedProcess(["ffprobe"], 1, "", "Invalid data")

            with patch.object(media_probe.subprocess, "run", return_value=failed_probe):
                report = preflight_media_files([path], MediaLimits())

            self.assertEqual(report.accepted, ())
            self.assertEqual(len(report.rejected), 1)
            self.assertIn("Media probe failed", report.rejected[0].message)

    def test_truncated_png_header_is_rejected_without_falling_back_to_ffprobe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "truncated.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01")

            with self.assertRaisesRegex(MediaProbeError, "Malformed PNG"):
                media_probe.probe_media(path)

    def test_valid_content_with_an_unexpected_extension_is_accepted_and_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scan.upload"
            path.write_bytes(_ONE_PIXEL_PNG)

            metadata = validate_media(path, MediaLimits())

            self.assertTrue(media_probe.is_candidate_media_file(path))
            self.assertEqual(metadata.actual_type, "image")
            self.assertFalse(metadata.extension_matches)

    def test_pixel_limit_and_carousel_limit_reject_the_whole_unsafe_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oversized = root / "large.png"
            oversized.write_bytes(_png_with_dimensions(2, 2))
            with self.assertRaisesRegex(MediaValidationError, "pixel count"):
                validate_media(oversized, MediaLimits(max_image_pixels=3))

            first = root / "first.png"
            second = root / "second.png"
            first.write_bytes(_ONE_PIXEL_PNG)
            second.write_bytes(_ONE_PIXEL_PNG)
            report = preflight_media_files([first, second], MediaLimits(max_carousel_images=1))

            self.assertEqual(report.accepted, ())
            self.assertEqual({issue.path.name for issue in report.rejected}, {"first.png", "second.png"})
            self.assertTrue(all("Carousel has 2 images" in issue.message for issue in report.rejected))

    def test_video_duration_and_stream_metadata_come_from_ffprobe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "long-video.bin"
            path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
            ffprobe_data = {
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "901.25"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }
            result = subprocess.CompletedProcess(["ffprobe"], 0, json.dumps(ffprobe_data), "")

            with patch.object(media_probe.subprocess, "run", return_value=result):
                with self.assertRaisesRegex(MediaValidationError, "Video duration"):
                    validate_media(path, MediaLimits(max_video_duration_seconds=900))
                metadata = media_probe.probe_media(path)

            self.assertEqual(metadata.actual_type, "video")
            self.assertEqual(metadata.codec, "h264")
            self.assertTrue(metadata.has_audio)
            self.assertEqual(metadata.audio_codec, "aac")
            self.assertEqual(metadata.stream_count, 2)
            self.assertFalse(metadata.extension_matches)

    def test_animated_gif_is_rejected_by_explicit_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "animated.gif"
            path.write_bytes(b"GIF89a\x01\x00\x01\x00\x80\x00\x00NETSCAPE2.0;")

            with self.assertRaisesRegex(MediaValidationError, "Animated GIF"):
                validate_media(path, MediaLimits())

    def test_generated_output_must_match_the_expected_type_and_dimensions(self) -> None:
        metadata = media_probe.MediaMetadata(
            path=Path("generated.mp4"),
            actual_type="video",
            format_name="mov,mp4",
            width=1080,
            height=1350,
            duration_seconds=4.0,
            codec="h264",
            stream_count=1,
            has_audio=False,
            audio_codec=None,
            byte_size=10,
            animated=False,
            extension_matches=True,
        )
        with patch.object(media_probe, "probe_media", return_value=metadata):
            with self.assertRaisesRegex(MediaValidationError, "height"):
                media_probe.verify_generated_media(Path("generated.mp4"), expected_type="video", width=1080, height=1920)


if __name__ == "__main__":
    unittest.main()
