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

from publishing import (  # noqa: E402
    PublishStatus,
    build_caption_export,
    build_initial_publishing_state,
    ensure_manifest_defaults,
    list_output_manifests,
    list_provider_names,
    load_manifest,
    normalize_hashtag_list,
    save_manifest,
    update_manifest_review,
)


class PublishingTests(unittest.TestCase):
    def test_registry_exposes_manual_export_provider(self) -> None:
        self.assertIn("manual_export", list_provider_names())

    def test_initial_publishing_state_uses_requested_workflow_status(self) -> None:
        state = build_initial_publishing_state(default_status=PublishStatus.DRAFT)
        self.assertEqual(state["workflow_status"], "draft")
        self.assertIn("manual_export", state["providers"])
        self.assertFalse(state["providers"]["manual_export"]["can_direct_publish"])

    def test_normalize_hashtag_list_handles_strings_and_dedupes(self) -> None:
        self.assertEqual(
            normalize_hashtag_list("#Nabisco, vintageads retro_toys #Nabisco"),
            ["nabisco", "vintageads", "retro_toys"],
        )

    def test_update_manifest_review_updates_content_and_history(self) -> None:
        manifest = ensure_manifest_defaults(
            {
                "post_id": "video-123",
                "post_type": "video",
                "content": {"title": "Old", "description": "Old desc", "hashtags": ["oldtag"], "details": ["Bike prizes"]},
                "analysis": {"meta": {"year": "1950s", "decade": "1950s", "brand": "Nabisco", "mood": "Excitement"}},
            }
        )

        updated = update_manifest_review(
            manifest,
            title="New Hook",
            description="Fresh copy for review.",
            hashtags="#Nabisco, ToyRoundUp",
            selected_providers=["manual_export"],
            workflow_status=PublishStatus.READY.value,
            note="Saved from test",
        )

        self.assertEqual(updated["content"]["title"], "New Hook")
        self.assertEqual(updated["content"]["hashtags"], ["nabisco", "toyroundup"])
        self.assertEqual(updated["publishing"]["workflow_status"], "ready")
        self.assertEqual(updated["publishing"]["selected_providers"], ["manual_export"])
        self.assertEqual(updated["publishing"]["history"][-1]["note"], "Saved from test")

    def test_save_manifest_updates_caption_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs_dir = root / "outputs" / "video-123"
            captions_dir = root / "captions"
            outputs_dir.mkdir(parents=True)
            captions_dir.mkdir(parents=True)

            manifest_path = outputs_dir / "post_manifest.json"
            manifest = ensure_manifest_defaults(
                {
                    "post_id": "video-123",
                    "post_type": "video",
                    "source_files": [{"filename": "clip.mp4"}],
                    "paths": {
                        "caption_path": "outputs/video-123/caption.txt",
                        "legacy_caption_path": "captions/clip.txt",
                    },
                    "content": {
                        "title": "Fresh Hook",
                        "description": "Description here.",
                        "hashtags": ["nabisco", "retroads"],
                        "details": ["Bike prizes"],
                    },
                    "analysis": {"meta": {"year": "Unknown", "decade": "1950s", "brand": "Nabisco", "mood": "Excitement"}},
                }
            )
            save_manifest(manifest_path, manifest)

            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("Fresh Hook", saved_manifest["content"]["caption_text"])
            self.assertNotIn("DETAILS PULLED FROM THE AD", saved_manifest["content"]["caption_text"])
            self.assertNotIn("Ready to post", saved_manifest["content"]["caption_text"])
            self.assertEqual(saved_manifest["content"]["details"], ["Bike prizes"])
            self.assertTrue((outputs_dir / "caption.txt").exists())
            self.assertTrue((captions_dir / "clip.txt").exists())

    def test_save_carousel_manifest_updates_clean_caption_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outputs_dir = root / "outputs" / "carousel-123"
            captions_dir = root / "captions"
            outputs_dir.mkdir(parents=True)
            captions_dir.mkdir(parents=True)

            manifest_path = outputs_dir / "post_manifest.json"
            manifest = ensure_manifest_defaults(
                {
                    "post_id": "carousel-123",
                    "post_type": "image_carousel",
                    "source_files": [{"filename": "one.jpg"}, {"filename": "two.jpg"}],
                    "paths": {
                        "caption_path": "outputs/carousel-123/caption.txt",
                        "legacy_caption_path": "captions/carousel.txt",
                    },
                    "content": {
                        "title": "1990s Game Informer: Magazine Ad Carousel",
                        "description": "A scan set full of bold game magazine layouts.",
                        "hashtags": ["gameinformer", "retroads"],
                        "details": ["Multiple magazine scans"],
                    },
                    "analysis": {"meta": {"year": "1994", "decade": "1990s", "brand": "Game Informer", "mood": "Collector"}},
                }
            )
            save_manifest(manifest_path, manifest)

            saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved_manifest["content"]["caption_text"],
                "1990s Game Informer: Magazine Ad Carousel\n\n"
                "A scan set full of bold game magazine layouts.\n\n"
                "#gameinformer #retroads\n",
            )
            self.assertNotIn("SET DETAILS", saved_manifest["content"]["caption_text"])
            self.assertNotIn("Included files", saved_manifest["content"]["caption_text"])
            self.assertNotIn("Ready to post", saved_manifest["content"]["caption_text"])
            self.assertEqual(saved_manifest["content"]["details"], ["Multiple magazine scans"])
            self.assertTrue((outputs_dir / "caption.txt").exists())
            self.assertTrue((captions_dir / "carousel.txt").exists())

    def test_list_output_manifests_finds_workspace_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs_dir = Path(temp_dir) / "outputs"
            (outputs_dir / "post-one").mkdir(parents=True)
            (outputs_dir / "post-two").mkdir(parents=True)
            (outputs_dir / "post-one" / "post_manifest.json").write_text("{}", encoding="utf-8")
            (outputs_dir / "post-two" / "post_manifest.json").write_text("{}", encoding="utf-8")

            manifests = list_output_manifests(outputs_dir)
            self.assertEqual(len(manifests), 2)
            self.assertTrue(all(path.name == "post_manifest.json" for path in manifests))

    def test_load_manifest_applies_missing_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "post_manifest.json"
            manifest_path.write_text('{"post_id":"abc"}', encoding="utf-8")
            manifest = load_manifest(manifest_path)
            self.assertEqual(manifest["post_id"], "abc")
            self.assertIn("publishing", manifest)
            self.assertIn("manual_export", manifest["publishing"]["providers"])
            self.assertEqual(build_caption_export(manifest).count("Ready to post"), 0)

    def test_record_provider_audit_appends_provider_history(self) -> None:
        from publishing import record_provider_audit

        manifest = ensure_manifest_defaults({"post_id": "abc"})

        updated = record_provider_audit(manifest, "manual_export", "prepare", "ready", "Prepared local export")

        audit = updated["publishing"]["provider_history"]
        self.assertEqual(audit[-1]["provider"], "manual_export")
        self.assertEqual(audit[-1]["action"], "prepare")
        self.assertEqual(audit[-1]["status"], "ready")
        self.assertEqual(audit[-1]["message"], "Prepared local export")


if __name__ == "__main__":
    unittest.main()
