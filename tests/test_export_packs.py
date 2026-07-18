from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from export_packs import create_posting_pack  # noqa: E402
from readiness import format_readiness_reports, readiness_reports_for_manifest, render_final_caption  # noqa: E402
from safe_paths import UnsafePathError  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def portrait_png() -> bytes:
    return _ONE_PIXEL_PNG[:16] + (1080).to_bytes(4, "big") + (1350).to_bytes(4, "big") + _ONE_PIXEL_PNG[24:]


class ExportPackTests(unittest.TestCase):
    def test_create_posting_pack_copies_caption_media_manifest_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "outputs" / "video-abc"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            (workspace / "caption.txt").write_text("Caption body\n#tagone #tagtwo", encoding="utf-8")
            (media_dir / "clip.png").write_bytes(portrait_png())
            manifest = {
                "post_id": "video-abc",
                "post_type": "video",
                "content": {
                    "title": "1991 Sega Blast",
                    "description": "Caption body",
                    "hashtags": ["tagone", "tagtwo"],
                },
                "media_files": [{"filename": "clip.png", "relative_path": "outputs/video-abc/media/clip.png"}],
                "paths": {"caption_path": "outputs/video-abc/caption.txt"},
                "publishing": {"workflow_status": "ready", "selected_providers": ["manual_export"]},
            }
            manifest_path = workspace / "post_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_posting_pack(manifest_path, root / "exports")

            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            reports = readiness_reports_for_manifest(manifest_path, ("manual_export", "instagram", "facebook"), manifest=saved_manifest)
            self.assertTrue((result.pack_dir / "caption.txt").exists())
            self.assertEqual((result.pack_dir / "caption.txt").read_text(encoding="utf-8"), render_final_caption(saved_manifest))
            self.assertEqual((result.pack_dir / "media" / "clip.png").read_bytes(), portrait_png())
            self.assertEqual((result.pack_dir / "hashtags.txt").read_text(encoding="utf-8"), "#tagone #tagtwo\n")
            self.assertTrue((result.pack_dir / "posting-notes.txt").read_text(encoding="utf-8").startswith("Title: 1991 Sega Blast"))
            self.assertTrue((result.pack_dir / "post_manifest.json").exists())
            self.assertEqual(
                (result.pack_dir / "platforms" / "platform-validation.txt").read_text(encoding="utf-8"),
                format_readiness_reports(reports),
            )
            self.assertEqual(result.media_count, 1)

    def test_create_posting_pack_writes_platform_notes_and_caption_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "outputs" / "video-abc"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            (workspace / "caption.txt").write_text("Caption body\n#tagone #tagtwo", encoding="utf-8")
            (media_dir / "clip.png").write_bytes(portrait_png())
            manifest = {
                "post_id": "video-abc",
                "post_type": "video",
                "content": {"title": "1991 Sega Blast", "description": "Caption body", "hashtags": ["tagone", "tagtwo"]},
                "media_files": [{"filename": "clip.png", "relative_path": "outputs/video-abc/media/clip.png", "width": 1080, "height": 1350}],
                "paths": {"caption_path": "outputs/video-abc/caption.txt"},
                "publishing": {"workflow_status": "ready", "selected_providers": ["manual_export"]},
            }
            manifest_path = workspace / "post_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_posting_pack(manifest_path, root / "exports", platforms=("instagram", "facebook"))

            self.assertTrue((result.pack_dir / "platforms" / "instagram-notes.txt").exists())
            self.assertTrue((result.pack_dir / "platforms" / "facebook-caption.txt").exists())

    def test_unsafe_manifest_media_path_preserves_existing_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "outputs" / "video-abc"
            workspace.mkdir(parents=True)
            outside = root / "outside.mp4"
            outside.write_bytes(b"outside")
            manifest_path = workspace / "post_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "post_id": "video-abc",
                        "media_files": [{"filename": "outside.mp4", "relative_path": "../outside.mp4"}],
                    }
                ),
                encoding="utf-8",
            )
            old_pack = root / "exports" / "posting-packs" / "video-abc"
            old_pack.mkdir(parents=True)
            marker = old_pack / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(UnsafePathError):
                create_posting_pack(manifest_path, root / "exports")

            self.assertTrue(outside.exists())
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
