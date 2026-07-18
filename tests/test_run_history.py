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

from run_history import (  # noqa: E402
    collect_failed_retry_candidates,
    format_run_details,
    format_run_history,
    list_recent_inbox_runs,
    load_inbox_run_details,
    summarize_inbox_run,
)


class RunHistoryTests(unittest.TestCase):
    def test_summarize_inbox_run_counts_status_sources_and_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "inbox-run-200.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "type": "video",
                            "file": "clip.mp4",
                            "status": "processed",
                            "analysis_source": "gemini_vision",
                            "publish_status": "ready",
                        },
                        {
                            "type": "image_carousel",
                            "files": ["one.jpg", "two.jpg", "three.jpg"],
                            "file_count": 3,
                            "status": "failed",
                            "analysis_source": "failed",
                            "error": "image_batch_move_failed",
                            "message": "disk full",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            summary = summarize_inbox_run(log_path)

            self.assertEqual(summary.status, "failed")
            self.assertEqual(summary.total_records, 2)
            self.assertEqual(summary.processed_count, 1)
            self.assertEqual(summary.failed_count, 1)
            self.assertEqual(summary.media_count, 4)
            self.assertEqual(summary.analysis_sources, ("failed", "gemini_vision"))
            self.assertEqual(summary.error_messages, ("image_batch_move_failed: disk full",))

    def test_list_recent_inbox_runs_sorts_newest_first_and_marks_unreadable_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir)
            (logs_dir / "inbox-run-100.json").write_text("[]", encoding="utf-8")
            (logs_dir / "inbox-run-300.json").write_text("not json", encoding="utf-8")
            (logs_dir / "other.json").write_text("[]", encoding="utf-8")

            summaries = list_recent_inbox_runs(logs_dir, limit=2)

            self.assertEqual([summary.path.name for summary in summaries], ["inbox-run-300.json", "inbox-run-100.json"])
            self.assertEqual(summaries[0].status, "unreadable")
            self.assertEqual(summaries[1].status, "empty")

    def test_format_run_history_surfaces_latest_failure_without_opening_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "inbox-run-400.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "type": "video",
                            "file": "bad.mp4",
                            "status": "failed",
                            "analysis_source": "gemini_vision",
                            "error": "video_conversion_failed",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            text = format_run_history([summarize_inbox_run(log_path)])

            self.assertIn("Latest Run: FAILED", text)
            self.assertIn("0 processed", text)
            self.assertIn("1 failed", text)
            self.assertIn("video_conversion_failed", text)

    def test_committed_archival_warning_is_visible_without_marking_the_media_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "inbox-run-warning.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "type": "video",
                            "file": "clip.mp4",
                            "status": "committed_with_archival_warning",
                            "warnings": ["Original source is waiting for archival recovery."],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            summary = summarize_inbox_run(log_path)

            self.assertEqual(summary.status, "warning")
            self.assertEqual(summary.processed_count, 1)
            self.assertEqual(summary.failed_count, 0)
            self.assertIn("Original source is waiting", summary.error_messages[0])

    def test_load_inbox_run_details_includes_paths_and_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "inbox-run-500.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "type": "video",
                            "file": "good.mp4",
                            "status": "processed",
                            "caption_path": str(Path(temp_dir) / "outputs" / "good" / "caption.txt"),
                            "output_dir": str(Path(temp_dir) / "outputs" / "good"),
                            "manifest_path": str(Path(temp_dir) / "outputs" / "good" / "post_manifest.json"),
                            "processed_media_path": str(Path(temp_dir) / "!processed" / "good.mp4"),
                            "analysis_source": "gemini_vision",
                            "publish_status": "ready",
                        },
                        {
                            "type": "image_carousel",
                            "status": "failed",
                            "files": ["one.jpg", "two.jpg"],
                            "error": "unhandled_exception",
                            "message": "Gemini down",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            details = load_inbox_run_details(log_path)

            self.assertEqual(details.summary.status, "failed")
            self.assertEqual([record.display_name for record in details.records], ["good.mp4", "one.jpg, two.jpg"])
            self.assertEqual(details.records[0].output_dir, Path(temp_dir) / "outputs" / "good")
            self.assertEqual(details.records[0].processed_media_paths, (Path(temp_dir) / "!processed" / "good.mp4",))
            self.assertEqual(details.records[1].error_message, "unhandled_exception: Gemini down")

    def test_format_run_details_lists_records_and_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "inbox-run-600.json"
            log_path.write_text(
                json.dumps(
                    [
                        {
                            "type": "image_carousel",
                            "status": "failed",
                            "files": ["ad-one.jpg"],
                            "analysis_source": "failed",
                            "analysis_error": "Gemini 503",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            text = format_run_details(load_inbox_run_details(log_path))

            self.assertIn("Run 600: FAILED", text)
            self.assertIn("ad-one.jpg", text)
            self.assertIn("Gemini 503", text)
            self.assertIn("Retry from inbox", text)

    def test_collect_failed_retry_candidates_only_returns_files_still_in_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "still-here.mp4").write_bytes(b"video")
            log_path = root / "logs" / "inbox-run-700.json"
            log_path.parent.mkdir()
            log_path.write_text(
                json.dumps(
                    [
                        {"type": "video", "file": "still-here.mp4", "status": "failed"},
                        {"type": "video", "file": "missing.mp4", "status": "failed"},
                    ]
                ),
                encoding="utf-8",
            )

            candidates = collect_failed_retry_candidates(log_path, inbox)

            self.assertEqual([candidate.name for candidate in candidates], ["still-here.mp4"])


if __name__ == "__main__":
    unittest.main()
