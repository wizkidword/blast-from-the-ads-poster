from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import readiness  # noqa: E402
from media_probe import MediaMetadata  # noqa: E402
from publishing import PublishStatus, load_manifest, save_manifest, update_manifest_review  # noqa: E402
from readiness import (  # noqa: E402
    ReadinessBlockedError,
    format_readiness_report,
    readiness_report_for_manifest,
    record_readiness_override,
)
from review_queue import readiness_reports_for_review  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def png(width: int = 1080, height: int = 1350) -> bytes:
    return _ONE_PIXEL_PNG[:16] + width.to_bytes(4, "big") + height.to_bytes(4, "big") + _ONE_PIXEL_PNG[24:]


class ReadinessTests(unittest.TestCase):
    def _workspace(self, *, post_type: str = "image_carousel", description: str = "A useful final caption.", count: int = 1) -> tuple[Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        workspace = root / "outputs" / "post-123"
        media_dir = workspace / "media"
        media_dir.mkdir(parents=True)
        (workspace / "caption.txt").write_text("placeholder", encoding="utf-8")
        media_files = []
        for index in range(1, count + 1):
            filename = f"slide-{index}.png"
            (media_dir / filename).write_bytes(png())
            media_files.append(
                {
                    "filename": filename,
                    "relative_path": f"outputs/post-123/media/{filename}",
                    "role": "carousel_item",
                    "width": 1080,
                    "height": 1350,
                }
            )
        manifest = {
            "post_id": "post-123",
            "post_type": post_type,
            "content": {"title": "A title", "description": description, "hashtags": ["retro"]},
            "media_files": media_files,
            "paths": {"caption_path": "outputs/post-123/caption.txt"},
            "publishing": {"workflow_status": "draft", "selected_providers": ["instagram"]},
        }
        manifest_path = workspace / "post_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return root, manifest_path

    def test_final_rendered_caption_length_blocks_even_when_description_alone_fits(self) -> None:
        _root, manifest_path = self._workspace(description="x" * 2_190)

        report = readiness_report_for_manifest(manifest_path, "instagram")

        self.assertFalse(report.ready)
        self.assertIn("caption_length", [check.code for check in report.blocking_failures])

    def test_missing_asset_and_wrong_aspect_ratio_are_blocking(self) -> None:
        _root, manifest_path = self._workspace()
        missing = readiness_report_for_manifest(manifest_path, "instagram")
        (manifest_path.parent / "media" / "slide-1.png").unlink()
        missing = readiness_report_for_manifest(manifest_path, "instagram")
        self.assertIn("asset_exists:1", [check.code for check in missing.blocking_failures])

        _root, ratio_manifest = self._workspace()
        (ratio_manifest.parent / "media" / "slide-1.png").write_bytes(png(1350, 1080))
        ratio = readiness_report_for_manifest(ratio_manifest, "instagram")
        self.assertIn("media_dimensions:1", [check.code for check in ratio.blocking_failures])

    def test_media_count_limit_blocks_platform_readiness(self) -> None:
        _root, manifest_path = self._workspace(count=11)

        report = readiness_report_for_manifest(manifest_path, "instagram")

        self.assertIn("media_count", [check.code for check in report.blocking_failures])

    def test_video_duration_size_and_codec_checks_are_explicit(self) -> None:
        root, manifest_path = self._workspace(post_type="video")
        media_dir = manifest_path.parent / "media"
        for item in media_dir.iterdir():
            item.unlink()
        video = media_dir / "clip.mp4"
        video.write_bytes(b"placeholder")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["media_files"] = [{"filename": "clip.mp4", "relative_path": "outputs/post-123/media/clip.mp4", "role": "primary"}]
        manifest["publishing"]["selected_providers"] = ["tiktok"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        metadata = MediaMetadata(
            path=video,
            actual_type="video",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            width=1080,
            height=1920,
            duration_seconds=601.0,
            codec="vp9",
            stream_count=1,
            has_audio=False,
            audio_codec=None,
            byte_size=1_000_000_001,
            animated=False,
            extension_matches=True,
        )

        with patch.object(readiness, "probe_media", return_value=metadata):
            report = readiness_report_for_manifest(manifest_path, "tiktok")

        codes = [check.code for check in report.blocking_failures]
        self.assertIn("media_size:1", codes)
        self.assertIn("video_duration:1", codes)
        self.assertIn("video_codec:1", codes)

    def test_ready_transition_requires_current_report_and_override_is_audited(self) -> None:
        _root, manifest_path = self._workspace(description="x" * 2_190)
        manifest = load_manifest(manifest_path)
        with self.assertRaisesRegex(ValueError, "readiness report"):
            update_manifest_review(
                manifest,
                title="A title",
                description="x" * 2_190,
                hashtags=["retro"],
                selected_providers=["instagram"],
                workflow_status=PublishStatus.READY.value,
                note="Attempt ready",
            )

        report = readiness_report_for_manifest(manifest_path, "instagram", manifest=manifest)
        overridden = record_readiness_override(manifest, report, ["caption_length"], "Approved for a one-off campaign")
        overridden_report = readiness_report_for_manifest(manifest_path, "instagram", manifest=overridden)
        self.assertTrue(overridden_report.ready)
        self.assertIn("Explicitly overridden", format_readiness_report(overridden_report))
        self.assertEqual(overridden["publishing"]["readiness_overrides"][-1]["reason"], "Approved for a one-off campaign")

    def test_review_uses_the_same_report_as_the_transition_gate(self) -> None:
        _root, manifest_path = self._workspace()
        manifest = load_manifest(manifest_path)

        review_reports = readiness_reports_for_review(manifest_path, manifest)
        direct = readiness_report_for_manifest(manifest_path, "instagram", manifest=manifest)
        updated = update_manifest_review(
            manifest,
            title="A title",
            description="A useful final caption.",
            hashtags=["retro"],
            selected_providers=["instagram"],
            workflow_status=PublishStatus.READY.value,
            note="Ready after review",
            readiness_reports=review_reports,
        )

        self.assertTrue(direct.ready)
        self.assertTrue(updated["publishing"]["workflow_status"] == "ready")


if __name__ == "__main__":
    unittest.main()
