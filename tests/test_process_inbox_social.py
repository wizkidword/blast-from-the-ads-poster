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

import process_inbox_social as processor  # noqa: E402
from process_inbox_social import (  # noqa: E402
    build_caption_block,
    build_caption_payload,
    build_carousel_caption_block,
    build_post_id,
    copy_processed_media_to_output,
    sanitize_slug,
)
from process_inbox_social import pick_representative_files  # noqa: E402
from run_ledger import normalize_run_log  # noqa: E402


class ProcessInboxSocialTests(unittest.TestCase):
    def test_sanitize_slug_collapses_noise(self) -> None:
        self.assertEqual(sanitize_slug("Nabisco Toy Round Up!!!"), "nabisco-toy-round-up")

    def test_build_post_id_includes_post_type_slug_and_digest(self) -> None:
        post_id = build_post_id("video", [Path("CLASSIC_KIDS_COMMERCIAL_1_Nabisco1.mp4")])
        self.assertRegex(post_id, r"^video-\d{8}-\d{6}-classic-kids-commercial-1-nabisco1-[a-f0-9]{8}$")

    def test_build_caption_payload_normalizes_hashtags(self) -> None:
        payload = build_caption_payload(
            {
                "title": "Ignored",
                "description": "Some copy",
                "hashtags": ["#Nabisco", "nabisco", "Vintage Ads", "retro toys"],
                "notable_details": ["Bikes", "Toy aisle", "Contest signage", "Black and white footage", "Extra item"],
            },
            "CLASSIC_KIDS_COMMERCIAL_1_Nabisco1.mp4",
        )
        self.assertEqual(payload["hashtags"][0], "nabisco")
        self.assertIn("#nabisco", payload["hashtag_block"])
        self.assertLessEqual(len(payload["details"]), 4)
        self.assertEqual(payload["description"], "Some copy")

    def test_build_video_caption_block_is_copy_paste_only(self) -> None:
        caption = build_caption_block(
            {
                "title": "1982 Milliken & Company: Commercial Break Classic",
                "description": "A stylish fabric commercial with a confident model.",
                "hashtags": ["milliken", "retroads"],
                "notable_details": ["Woman models a red tailored outfit"],
                "year": "1982",
                "decade": "1980s",
                "brand": "Milliken & Company",
                "mood": "Stylish",
            },
            "007 - Vintage 1980s Milliken Visa Fabric Old Commercial.mp4",
        )

        self.assertEqual(
            caption,
            "1982 Milliken & Company: Commercial Break Classic\n\n"
            "A stylish fabric commercial with a confident model.\n\n"
            "#milliken #retroads #blastfromtheads #vintageads #nostalgia #throwback #retroculture\n",
        )
        self.assertNotIn("CAPTION (copy-paste ready)", caption)
        self.assertNotIn("Analysis:", caption)
        self.assertNotIn("DETAILS PULLED FROM THE AD", caption)
        self.assertNotIn("Ready to post", caption)

    def test_build_carousel_caption_block_is_copy_paste_only(self) -> None:
        caption = build_carousel_caption_block(
            {
                "title": "1990s Game Informer: Magazine Ad Carousel",
                "description": "A scan set full of bold game magazine layouts.",
                "hashtags": ["gameinformer", "retroads"],
                "notable_details": ["Multiple magazine scans", "Bold console artwork"],
                "year": "1994",
                "decade": "1990s",
                "brand": "Game Informer",
                "mood": "Collector",
            },
            [Path("Gameinformer - 34 - 05.jpg"), Path("Gameinformer - 34 - 07.jpg")],
        )

        self.assertEqual(
            caption,
            "1990s Game Informer: Magazine Ad Carousel\n\n"
            "A scan set full of bold game magazine layouts.\n\n"
            "#gameinformer #retroads #blastfromtheads #carousel #vintageads #nostalgia #throwback #retroculture #adarchive\n",
        )
        self.assertNotIn("CAROUSEL CAPTION (copy-paste ready)", caption)
        self.assertNotIn("Analysis:", caption)
        self.assertNotIn("Included files", caption)
        self.assertNotIn("SET DETAILS", caption)
        self.assertNotIn("Ready to post", caption)

    def test_copy_processed_media_to_output_copies_file_into_media_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            processed_dir.mkdir()
            outputs_dir.mkdir()
            processed_file = processed_dir / "CAP_N_CRUNCH.mp4"
            processed_file.write_bytes(b"video-bytes")
            output_dir = outputs_dir / "workspace"
            (output_dir / "media").mkdir(parents=True)

            copied_path = copy_processed_media_to_output(
                processed_file,
                output_dir,
                processed_root=processed_dir,
                outputs_root=outputs_dir,
            )

            self.assertEqual(copied_path, (output_dir / "media" / processed_file.name).resolve())
            self.assertTrue(copied_path.exists())
            self.assertEqual(copied_path.read_bytes(), b"video-bytes")

    def test_pick_representative_files_spreads_selection_across_batch(self) -> None:
        files = [Path(f"image-{index}.jpg") for index in range(9)]
        picked = pick_representative_files(files, 4)
        self.assertEqual([path.name for path in picked], ["image-0.jpg", "image-3.jpg", "image-5.jpg", "image-8.jpg"])

    def test_video_conversion_failure_leaves_original_in_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "raw-commercial.mp4"
            destination = root / "processed" / "raw-commercial.mp4"
            destination.parent.mkdir()
            source.write_bytes(b"original-video")

            with patch.object(processor, "convert_video_to_vertical", return_value=False):
                processed_path = processor.handle_video_conversion_and_move(
                    source,
                    destination,
                    inbox_root=root,
                    processed_root=destination.parent,
                )

            self.assertIsNone(processed_path)
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"original-video")
            self.assertFalse(destination.exists())

    def test_instagram_video_destination_always_uses_mp4_container(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            processed_dir = Path(temp_dir) / "processed"
            processed_dir.mkdir()
            destination = processor.instagram_video_destination(Path("arcade-ad.mov"), processed_dir)
            self.assertEqual(destination, processed_dir.resolve() / "arcade-ad.mp4")

    def test_video_target_dimensions_are_full_vertical_reel_size(self) -> None:
        self.assertEqual((processor.INSTAGRAM_VIDEO_WIDTH, processor.INSTAGRAM_VIDEO_HEIGHT), (1080, 1920))

    def test_process_video_file_fails_when_conversion_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir):
                directory.mkdir()
            source = inbox_dir / "arcade-ad.mp4"
            source.write_bytes(b"original-video")
            meta = {
                "title": "Arcade Ad",
                "description": "A specific arcade commercial.",
                "hashtags": ["arcade", "retroads"],
                "notable_details": ["cabinet"],
                "year": "1982",
                "decade": "1980s",
                "brand": "Arcade",
            }

            with (
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "extract_video_frames", return_value=[]),
                patch.object(processor, "analyze_with_fallback", return_value=(meta, "gemini_vision", None)),
                patch.object(processor, "handle_video_conversion_and_move", return_value=None),
            ):
                result = processor.process_video_file(source)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "video_conversion_failed")
            self.assertTrue(source.exists())
            self.assertFalse(any(outputs_dir.iterdir()))

    def test_run_inbox_processing_records_unhandled_video_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            logs_dir = root / "logs"
            temp_path = root / "temp"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir, logs_dir, temp_path):
                directory.mkdir()
            source = inbox_dir / "broken-ad.mp4"
            source.write_bytes(b"video")

            with (
                patch.object(processor, "BASE_DIR", root),
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "LOGS_DIR", logs_dir),
                patch.object(processor, "TEMP_DIR", temp_path),
                patch.object(processor, "load_env", return_value=None),
                patch.object(processor, "get_openai_api_key", return_value="fake-key"),
                patch.object(processor, "process_video_file", side_effect=RuntimeError("boom")),
                patch.object(processor, "utc_now_iso", side_effect=["2026-07-18T12:00:00Z", "2026-07-18T12:01:00Z"]),
            ):
                summary = processor.run_inbox_processing()

            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0]["status"], "failed")
            self.assertEqual(summary[0]["error"], "unhandled_exception")
            self.assertIn("boom", summary[0]["message"])

            logs = list(logs_dir.glob("inbox-run-*.json"))
            self.assertEqual(len(logs), 1)
            logged = normalize_run_log(logs[0])
            self.assertEqual(logged["records"][0]["status"], "failed")
            self.assertEqual(logged["run"]["started_at"], "2026-07-18T12:00:00Z")
            self.assertEqual(logged["run"]["ended_at"], "2026-07-18T12:01:00Z")

    def test_run_inbox_processing_can_target_specific_retry_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            logs_dir = root / "logs"
            for directory in (inbox_dir, root / "captions", root / "processed", root / "outputs", logs_dir, root / "temp"):
                directory.mkdir()
            retry = inbox_dir / "retry-me.mp4"
            other = inbox_dir / "leave-me.mp4"
            retry.write_bytes(b"retry")
            other.write_bytes(b"other")

            def fake_process(path: Path, dry_run: bool = False, **_kwargs) -> dict:
                return {"type": "video", "file": path.name, "status": "processed"}

            with (
                patch.object(processor, "BASE_DIR", root),
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "LOGS_DIR", logs_dir),
                patch.object(processor, "load_env", return_value=None),
                patch.object(processor, "ensure_dirs", return_value=None),
                patch.object(processor, "get_openai_api_key", return_value="fake-key"),
                patch.object(processor, "process_video_file", side_effect=fake_process),
            ):
                summary = processor.run_inbox_processing(target_files=[retry])

            self.assertEqual([item["file"] for item in summary], ["retry-me.mp4"])

    def test_run_inbox_processing_refuses_target_outside_inbox_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            logs_dir = root / "logs"
            for directory in (inbox_dir, root / "captions", root / "processed", root / "outputs", logs_dir, root / "temp"):
                directory.mkdir()
            outside = root / "outside.mp4"
            outside.write_bytes(b"outside")

            with (
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "LOGS_DIR", logs_dir),
                patch.object(processor, "load_env", return_value=None),
                patch.object(processor, "ensure_dirs", return_value=None),
                patch.object(processor, "get_openai_api_key", return_value="fake-key"),
            ):
                summary = processor.run_inbox_processing(target_files=[outside])

            self.assertEqual(summary[0]["error"], "unsafe_target_path")
            self.assertTrue(outside.exists())
            self.assertEqual(list(inbox_dir.iterdir()), [])

    def test_process_image_batch_rolls_back_partial_moves_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir):
                directory.mkdir()
            first = inbox_dir / "ad-one.jpg"
            second = inbox_dir / "ad-two.jpg"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            meta = {
                "title": "Toy Ads",
                "description": "A specific carousel.",
                "hashtags": ["toys", "retroads"],
                "notable_details": ["box art"],
                "year": "1988",
                "decade": "1980s",
                "brand": "Toys",
            }

            def fake_move(file_path: Path, destination: Path, dry_run: bool = False, **_kwargs) -> Path:
                if file_path == first:
                    destination.write_bytes(b"processed-first")
                    file_path.unlink()
                    return destination
                raise RuntimeError("disk full")

            with (
                patch.object(processor, "BASE_DIR", root),
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "analyze_image_batch_with_fallback", return_value=(meta, "gemini_vision", None)),
                patch.object(processor, "handle_image_conversion_and_move", side_effect=fake_move),
            ):
                result = processor.process_image_batch([first, second])

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "image_batch_move_failed")
            self.assertTrue((inbox_dir / "ad-one.jpg").exists())
            self.assertTrue(second.exists())
            self.assertFalse(any(captions_dir.iterdir()))
            self.assertFalse(any(outputs_dir.iterdir()))
            self.assertFalse(any(processed_dir.iterdir()))

    def test_process_image_batch_creates_tiktok_ready_carousel_video(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir):
                directory.mkdir()
            first = inbox_dir / "ad-one.jpg"
            second = inbox_dir / "ad-two.jpg"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            meta = {
                "title": "Toy Ads",
                "description": "A nostalgic carousel.",
                "hashtags": ["toys", "retroads"],
                "notable_details": ["box art"],
                "year": "1988",
                "decade": "1980s",
                "brand": "Toys",
            }

            def fake_move(file_path: Path, destination: Path, dry_run: bool = False, **_kwargs) -> Path:
                destination.write_bytes(file_path.read_bytes())
                file_path.unlink()
                return destination

            def fake_video(image_paths: list[Path], destination: Path, dry_run: bool = False, **_kwargs) -> Path:
                self.assertEqual([path.name for path in image_paths], ["ad-one.jpg", "ad-two.jpg"])
                destination.write_bytes(b"carousel-video")
                return destination

            with (
                patch.object(processor, "BASE_DIR", root),
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "analyze_image_batch_with_fallback", return_value=(meta, "openai_vision", None)),
                patch.object(processor, "handle_image_conversion_and_move", side_effect=fake_move),
                patch.object(processor, "handle_carousel_video_creation", side_effect=fake_video),
            ):
                result = processor.process_image_batch([first, second])

            self.assertEqual(result["status"], "processed")
            self.assertTrue(str(result["carousel_video_path"]).endswith(".mp4"))
            output_dirs = list(outputs_dir.iterdir())
            self.assertEqual(len(output_dirs), 1)
            manifest = json.loads((output_dirs[0] / "post_manifest.json").read_text(encoding="utf-8"))
            roles = [item["role"] for item in manifest["media_files"]]
            self.assertEqual(roles, ["carousel_item", "carousel_item", "carousel_video"])
            video_record = manifest["media_files"][2]
            self.assertEqual(video_record["mime_type"], "video/mp4")
            self.assertEqual(
                video_record["relative_path"],
                (Path("outputs") / output_dirs[0].name / "tiktok" / "media" / video_record["filename"]).as_posix(),
            )
            self.assertTrue((output_dirs[0] / "tiktok" / "media" / video_record["filename"]).exists())
            self.assertFalse((output_dirs[0] / "media" / video_record["filename"]).exists())
            self.assertEqual(list((output_dirs[0] / "media").glob("*.mp4")), [])

    def test_process_image_batch_rolls_back_images_when_carousel_video_creation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir):
                directory.mkdir()
            first = inbox_dir / "ad-one.jpg"
            second = inbox_dir / "ad-two.jpg"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            meta = {
                "title": "Toy Ads",
                "description": "A nostalgic carousel.",
                "hashtags": ["toys", "retroads"],
                "notable_details": ["box art"],
                "year": "1988",
                "decade": "1980s",
                "brand": "Toys",
            }

            def fake_move(file_path: Path, destination: Path, dry_run: bool = False, **_kwargs) -> Path:
                destination.write_bytes(file_path.read_bytes())
                file_path.unlink()
                return destination

            with (
                patch.object(processor, "INBOX_DIR", inbox_dir),
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "analyze_image_batch_with_fallback", return_value=(meta, "openai_vision", None)),
                patch.object(processor, "handle_image_conversion_and_move", side_effect=fake_move),
                patch.object(processor, "handle_carousel_video_creation", return_value=None),
            ):
                result = processor.process_image_batch([first, second])

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"], "image_batch_move_failed")
            self.assertIn("carousel video", result["message"].lower())
            self.assertTrue((inbox_dir / "ad-one.jpg").exists())
            self.assertTrue((inbox_dir / "ad-two.jpg").exists())
            self.assertFalse(any(captions_dir.iterdir()))
            self.assertFalse(any(outputs_dir.iterdir()))
            self.assertFalse(any(processed_dir.iterdir()))

    def test_process_video_file_removes_extracted_temp_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox_dir = root / "inbox"
            captions_dir = root / "captions"
            processed_dir = root / "processed"
            outputs_dir = root / "outputs"
            temp_path = root / "temp"
            for directory in (inbox_dir, captions_dir, processed_dir, outputs_dir, temp_path):
                directory.mkdir()
            source = inbox_dir / "arcade-ad.mp4"
            source.write_bytes(b"original-video")
            frame_one = temp_path / "frame-one.jpg"
            frame_two = temp_path / "frame-two.jpg"
            frame_one.write_bytes(b"frame-one")
            frame_two.write_bytes(b"frame-two")
            processed_media = processed_dir / "arcade-ad.mp4"
            meta = {
                "title": "Arcade Ad",
                "description": "A specific arcade commercial.",
                "hashtags": ["arcade", "retroads"],
                "notable_details": ["cabinet"],
                "year": "1982",
                "decade": "1980s",
                "brand": "Arcade",
            }

            def fake_move(_file_path: Path, _destination: Path, dry_run: bool = False, **_kwargs) -> Path:
                processed_media.write_bytes(b"processed-video")
                return processed_media

            with (
                patch.object(processor, "CAPTIONS_DIR", captions_dir),
                patch.object(processor, "PROCESSED_DIR", processed_dir),
                patch.object(processor, "OUTPUTS_DIR", outputs_dir),
                patch.object(processor, "TEMP_DIR", temp_path),
                patch.object(processor, "extract_video_frames", return_value=[frame_one, frame_two]),
                patch.object(processor, "analyze_with_fallback", return_value=(meta, "gemini_vision", None)),
                patch.object(processor, "handle_video_conversion_and_move", side_effect=fake_move),
            ):
                result = processor.process_video_file(source)

            self.assertEqual(result["status"], "processed")
            self.assertFalse(frame_one.exists())
            self.assertFalse(frame_two.exists())


if __name__ == "__main__":
    unittest.main()
