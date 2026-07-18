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

from review_queue import bulk_update_status, format_review_preview, query_review_items  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def portrait_png() -> bytes:
    return _ONE_PIXEL_PNG[:16] + (1080).to_bytes(4, "big") + (1350).to_bytes(4, "big") + _ONE_PIXEL_PNG[24:]


def write_manifest(folder: Path, *, post_id: str, status: str, title: str, brand: str, year: str, extension: str = ".mp4") -> Path:
    folder.mkdir(parents=True)
    manifest = {
        "post_id": post_id,
        "post_type": "video",
        "updated_at": "2026-05-03T00:00:00Z",
        "source_files": [{"filename": f"{post_id}{extension}"}],
        "media_files": [{"filename": f"{post_id}{extension}", "relative_path": f"outputs/{post_id}/media/{post_id}{extension}"}],
        "analysis": {"source": "gemini_vision", "error": None, "meta": {"brand": brand, "year": year, "decade": "1990s"}},
        "content": {
            "title": title,
            "description": "A specific caption with useful visible details.",
            "hashtags": ["blastfromtheads", brand.lower().replace(" ", "")],
            "details": ["bright logo", "price burst"],
        },
        "paths": {"caption_path": f"outputs/{post_id}/caption.txt"},
        "publishing": {"workflow_status": status, "selected_providers": ["manual_export"], "providers": {}, "history": []},
    }
    path = folder / "post_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class ReviewQueueTests(unittest.TestCase):
    def test_query_review_items_filters_status_and_searches_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = Path(temp_dir)
            write_manifest(outputs / "ready-post", post_id="ready-post", status="ready", title="1991 Sega Blast", brand="Sega", year="1991")
            write_manifest(outputs / "draft-post", post_id="draft-post", status="draft", title="Nintendo Shelf Gem", brand="Nintendo", year="1989")

            items = query_review_items(outputs, status_filter="ready", search_text="sega")

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].post_id, "ready-post")
            self.assertEqual(items[0].label, "[READY] video | 1991 | Sega | 1991 Sega Blast")

    def test_format_review_preview_includes_caption_media_and_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = write_manifest(
                Path(temp_dir) / "ready-post",
                post_id="ready-post",
                status="ready",
                title="1991 Sega Blast",
                brand="Sega",
                year="1991",
            )

            item = query_review_items(Path(temp_dir), status_filter="all", search_text="")[0]
            preview = format_review_preview(item)

            self.assertIn("1991 Sega Blast", preview)
            self.assertIn("A specific caption", preview)
            self.assertIn("ready-post.mp4", preview)
            self.assertIn("#blastfromtheads", preview)
            self.assertEqual(item.manifest_path, manifest_path.resolve())

    def test_query_review_items_can_filter_stale_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = Path(temp_dir)
            manifest_path = write_manifest(outputs / "draft-post", post_id="draft-post", status="draft", title="Old Draft", brand="Sega", year="1991")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["updated_at"] = "2026-01-01T00:00:00Z"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            items = query_review_items(outputs, status_filter="stale_drafts", search_text="", now_iso="2026-05-03T00:00:00Z", stale_days=30)

            self.assertEqual([item.post_id for item in items], ["draft-post"])

    def test_bulk_update_status_changes_manifest_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs = root / "outputs"
            manifest_path = write_manifest(
                outputs / "draft-post",
                post_id="draft-post",
                status="draft",
                title="Draft",
                brand="Sega",
                year="1991",
                extension=".png",
            )
            (manifest_path.parent / "caption.txt").write_text("Draft\n\nA specific caption with useful visible details.\n\n#tag\n", encoding="utf-8")
            media_dir = manifest_path.parent / "media"
            media_dir.mkdir()
            (media_dir / "draft-post.png").write_bytes(portrait_png())

            count = bulk_update_status([manifest_path], "ready", note="Bulk marked ready")

            self.assertEqual(count, 1)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["publishing"]["workflow_status"], "ready")
            self.assertIn("Bulk marked ready", manifest["publishing"]["history"][-1]["note"])


if __name__ == "__main__":
    unittest.main()
