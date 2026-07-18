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

import export_packs  # noqa: E402
from export_packs import PostingPackExportError, PostingPackIntegrityError, create_posting_pack, verify_posting_pack  # noqa: E402
from readiness import format_readiness_reports, readiness_reports_for_manifest, render_final_caption  # noqa: E402
from safe_paths import UnsafePathError  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def portrait_png() -> bytes:
    return _ONE_PIXEL_PNG[:16] + (1080).to_bytes(4, "big") + (1350).to_bytes(4, "big") + _ONE_PIXEL_PNG[24:]


def create_ready_workspace(root: Path, *, sources: list[Path] | None = None) -> tuple[Path, Path]:
    workspace = root / "outputs" / "video-abc"
    media_dir = workspace / "media"
    media_dir.mkdir(parents=True)
    (workspace / "caption.txt").write_text("Caption body\n#tagone #tagtwo", encoding="utf-8")
    if sources is None:
        source = media_dir / "clip.png"
        source.write_bytes(portrait_png())
        sources = [source]
    manifest = {
        "post_id": "video-abc",
        "post_type": "video",
        "content": {
            "title": "1991 Sega Blast",
            "description": "Caption body",
            "hashtags": ["tagone", "tagtwo"],
        },
        "media_files": [
            {"filename": source.name, "relative_path": source.relative_to(root).as_posix()} for source in sources
        ],
        "paths": {"caption_path": "outputs/video-abc/caption.txt"},
        "publishing": {"workflow_status": "ready", "selected_providers": ["manual_export"]},
    }
    manifest_path = workspace / "post_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return workspace, manifest_path


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
            integrity = verify_posting_pack(result.pack_dir)
            self.assertEqual(integrity["source_manifest"], "outputs/video-abc/post_manifest.json")
            self.assertEqual(integrity["media"][0]["path"], "media/clip.png")
            self.assertEqual(integrity["media"][0]["order"], 1)

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

    def test_missing_media_blocks_export_without_touching_existing_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing = root / "outputs" / "video-abc" / "media" / "missing.png"
            _, manifest_path = create_ready_workspace(root, sources=[missing])
            old_pack = root / "exports" / "posting-packs" / "video-abc"
            old_pack.mkdir(parents=True)
            marker = old_pack / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(UnsafePathError):
                create_posting_pack(manifest_path, root / "exports")

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_duplicate_media_basenames_receive_deterministic_ordered_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "source-a" / "clip.png"
            second = root / "source-b" / "clip.png"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(portrait_png())
            second.write_bytes(portrait_png())
            _, manifest_path = create_ready_workspace(root, sources=[first, second])

            result = create_posting_pack(manifest_path, root / "exports", platforms=("manual_export",))

            integrity = verify_posting_pack(result.pack_dir)
            self.assertEqual([entry["filename"] for entry in integrity["media"]], ["01-clip.png", "02-clip.png"])
            self.assertTrue((result.pack_dir / "media" / "01-clip.png").exists())
            self.assertTrue((result.pack_dir / "media" / "02-clip.png").exists())

    def test_failed_staging_copy_preserves_existing_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = create_ready_workspace(root)
            packs_root = root / "exports" / "posting-packs"
            old_pack = packs_root / "video-abc"
            old_pack.mkdir(parents=True)
            marker = old_pack / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            original_copy2 = export_packs.shutil.copy2

            def fail_media_copy(source, destination, *args, **kwargs):
                if Path(destination).parent.name == "media":
                    raise OSError("simulated copy failure")
                return original_copy2(source, destination, *args, **kwargs)

            with patch("export_packs.shutil.copy2", side_effect=fail_media_copy):
                with self.assertRaises(OSError):
                    create_posting_pack(manifest_path, root / "exports")

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual([path.name for path in packs_root.iterdir()], ["video-abc"])

    def test_invalid_platform_does_not_create_or_replace_a_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = create_ready_workspace(root)
            old_pack = root / "exports" / "posting-packs" / "video-abc"
            old_pack.mkdir(parents=True)
            marker = old_pack / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(PostingPackExportError):
                create_posting_pack(manifest_path, root / "exports", platforms=("not-a-platform",))

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_hash_mismatch_is_detected_after_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = create_ready_workspace(root)
            result = create_posting_pack(manifest_path, root / "exports")
            (result.pack_dir / "media" / "clip.png").write_bytes(b"tampered")

            with self.assertRaises(PostingPackIntegrityError):
                verify_posting_pack(result.pack_dir)

    def test_failure_immediately_before_final_swap_restores_existing_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = create_ready_workspace(root)
            packs_root = root / "exports" / "posting-packs"
            old_pack = packs_root / "video-abc"
            old_pack.mkdir(parents=True)
            marker = old_pack / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            original_replace = export_packs.os.replace

            def fail_final_swap(source, destination):
                source_path = Path(source)
                if source_path.is_dir() and source_path.name.endswith(".tmp"):
                    raise OSError("simulated final replacement failure")
                return original_replace(source, destination)

            with patch("export_packs.os.replace", side_effect=fail_final_swap):
                with self.assertRaises(PostingPackExportError):
                    create_posting_pack(manifest_path, root / "exports")

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual([path.name for path in packs_root.iterdir()], ["video-abc"])


if __name__ == "__main__":
    unittest.main()
