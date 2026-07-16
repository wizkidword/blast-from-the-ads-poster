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


class ExportPackTests(unittest.TestCase):
    def test_create_posting_pack_copies_caption_media_manifest_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "outputs" / "video-abc"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            (workspace / "caption.txt").write_text("Caption body\n#tagone #tagtwo", encoding="utf-8")
            (media_dir / "clip.mp4").write_bytes(b"video")
            manifest = {
                "post_id": "video-abc",
                "post_type": "video",
                "content": {
                    "title": "1991 Sega Blast",
                    "description": "Caption body",
                    "hashtags": ["tagone", "tagtwo"],
                },
                "media_files": [{"filename": "clip.mp4", "relative_path": "outputs/video-abc/media/clip.mp4"}],
                "paths": {"caption_path": "outputs/video-abc/caption.txt"},
                "publishing": {"workflow_status": "ready", "selected_providers": ["manual_export"]},
            }
            manifest_path = workspace / "post_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_posting_pack(manifest_path, root / "exports")

            self.assertTrue((result.pack_dir / "caption.txt").exists())
            self.assertEqual((result.pack_dir / "media" / "clip.mp4").read_bytes(), b"video")
            self.assertEqual((result.pack_dir / "hashtags.txt").read_text(encoding="utf-8"), "#tagone #tagtwo\n")
            self.assertTrue((result.pack_dir / "posting-notes.txt").read_text(encoding="utf-8").startswith("Title: 1991 Sega Blast"))
            self.assertTrue((result.pack_dir / "post_manifest.json").exists())
            self.assertEqual(result.media_count, 1)

    def test_create_posting_pack_writes_platform_notes_and_caption_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "outputs" / "video-abc"
            media_dir = workspace / "media"
            media_dir.mkdir(parents=True)
            (workspace / "caption.txt").write_text("Caption body\n#tagone #tagtwo", encoding="utf-8")
            (media_dir / "clip.mp4").write_bytes(b"video")
            manifest = {
                "post_id": "video-abc",
                "post_type": "video",
                "content": {"title": "1991 Sega Blast", "description": "Caption body", "hashtags": ["tagone", "tagtwo"]},
                "media_files": [{"filename": "clip.mp4", "relative_path": "outputs/video-abc/media/clip.mp4", "width": 1080, "height": 1350}],
                "paths": {"caption_path": "outputs/video-abc/caption.txt"},
                "publishing": {"workflow_status": "ready", "selected_providers": ["manual_export"]},
            }
            manifest_path = workspace / "post_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = create_posting_pack(manifest_path, root / "exports", platforms=("instagram", "facebook"))

            self.assertTrue((result.pack_dir / "platforms" / "instagram-notes.txt").exists())
            self.assertTrue((result.pack_dir / "platforms" / "facebook-caption.txt").exists())


if __name__ == "__main__":
    unittest.main()
