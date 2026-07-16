from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_review import build_review_context_text, build_review_editor_state, build_review_label  # noqa: E402


class DesktopReviewTests(unittest.TestCase):
    def _manifest(self) -> dict:
        return {
            "post_id": "video-123",
            "post_type": "video",
            "updated_at": "2026-05-03T12:00:00Z",
            "source_files": [{"filename": "raw-ad.mp4"}],
            "media_files": [{"filename": "raw-ad.mp4", "mime_type": "video/mp4"}],
            "analysis": {
                "source": "gemini_vision",
                "error": None,
                "meta": {"year": "1984", "decade": "1980s", "brand": "Atari", "mood": "Electric"},
            },
            "content": {
                "title": "1984 Atari: Arcade Energy",
                "description": "A specific arcade spot.",
                "hashtags": ["atari", "retroads"],
                "details": ["neon cabinet", "fast cuts"],
            },
            "publishing": {
                "workflow_status": "ready",
                "selected_providers": ["manual_export"],
                "history": [
                    {"timestamp": "2026-05-03T12:01:00Z", "workflow_status": "ready", "note": "Reviewed"},
                ],
            },
        }

    def test_build_review_label_matches_queue_format(self) -> None:
        label = build_review_label(self._manifest())
        self.assertEqual(label, "[READY] video: 1984 Atari: Arcade Energy")

    def test_build_review_context_text_includes_analysis_media_and_history(self) -> None:
        context = build_review_context_text(self._manifest())
        self.assertIn("Post ID: video-123", context)
        self.assertIn("Analysis source: gemini_vision", context)
        self.assertIn("- raw-ad.mp4 (video/mp4)", context)
        self.assertIn("- neon cabinet", context)
        self.assertIn("Reviewed", context)

    def test_build_review_editor_state_extracts_editable_fields_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "outputs" / "video-123" / "post_manifest.json"
            manifest_path.parent.mkdir(parents=True)

            state = build_review_editor_state(
                self._manifest(),
                manifest_path,
                review_preview="Preview block",
            )

            self.assertEqual(state.selection_text, "Selected: video-123")
            self.assertIn("Status: ready", state.meta_text)
            self.assertEqual(state.title, "1984 Atari: Arcade Energy")
            self.assertEqual(state.description, "A specific arcade spot.")
            self.assertEqual(state.hashtags_text, "atari, retroads")
            self.assertEqual(state.selected_providers, ["manual_export"])
            self.assertTrue(state.context_text.startswith("Preview block"))


if __name__ == "__main__":
    unittest.main()
