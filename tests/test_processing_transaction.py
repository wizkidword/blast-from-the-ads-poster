from __future__ import annotations

import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app_context import build_app_context, prepare_app_context  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402
from processing_transaction import (  # noqa: E402
    ProcessingTransaction,
    TransactionState,
    recover_incomplete_transactions,
)
import processing_transaction as transactions  # noqa: E402
from workspace_lock import claim_inbox_files  # noqa: E402


_ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x80\x02\x00"
    b"{\x1e\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ProcessingTransactionTests(unittest.TestCase):
    def _context_and_claim(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        context = prepare_app_context(build_app_context(root))
        source = context.inbox_dir / "ad.jpg"
        source.write_bytes(_ONE_PIXEL_PNG)
        claims = claim_inbox_files(context.inbox_dir, [source], "run-1")
        return temporary, context, source, claims

    def test_precommit_rollback_restores_the_original_byte_for_byte(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            original_bytes = claims[0].claimed_path.read_bytes()
            transaction = ProcessingTransaction(context, "run-1", claims, "image_carousel")
            transaction.start("image-carousel-test")
            result = transaction.rollback("injected conversion failure")

            self.assertEqual(result.state, TransactionState.ROLLED_BACK)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertFalse(transaction.staging_root.exists())
            self.assertFalse(transaction.final_workspace.exists())

    def test_caption_checkpoint_failure_rolls_back_before_any_final_output(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            def fail_after_caption(checkpoint: str) -> None:
                if checkpoint == "after_caption_generation":
                    raise RuntimeError("injected caption interruption")

            transaction = ProcessingTransaction(
                context,
                "run-1",
                claims,
                "image_carousel",
                failure_injector=fail_after_caption,
            )
            transaction.start("image-carousel-test")
            created_at = json.loads(transaction.journal_path.read_text(encoding="utf-8"))["created_at"]
            with self.assertRaisesRegex(RuntimeError, "caption interruption"):
                transaction.write_caption("Caption", "ad.txt")
            journal_after_caption = json.loads(transaction.journal_path.read_text(encoding="utf-8"))
            result = transaction.rollback("injected caption interruption")

            self.assertEqual(result.state, TransactionState.ROLLED_BACK)
            self.assertTrue(source.exists())
            self.assertFalse(transaction.staging_root.exists())
            self.assertFalse((context.outputs_dir / "image-carousel-test").exists())
            self.assertEqual(journal_after_caption["created_at"], created_at)

    def test_recovery_keeps_claim_when_a_committed_workspace_is_missing(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            transaction = ProcessingTransaction(context, "run-1", claims, "video")
            transaction.start("missing-workspace")
            transaction.state = TransactionState.COMMITTED
            transaction.final_workspace = context.outputs_dir / "missing-workspace"
            transaction._write_journal()

            recovered = recover_incomplete_transactions(context)

            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].state, TransactionState.COMMITTED)
            self.assertIn("workspace is missing", recovered[0].message)
            self.assertTrue(claims[0].claimed_path.exists())
            self.assertFalse(source.exists())

    def test_commit_keeps_final_workspace_then_archives_exact_original(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            original_bytes = claims[0].claimed_path.read_bytes()
            transaction = ProcessingTransaction(context, "run-1", claims, "image_carousel")
            workspace, working_sources = transaction.start("image-carousel-test")
            staged_processed = transaction.staged_processed_path("ad.jpg")
            staged_processed.write_bytes(working_sources[0].read_bytes())
            staged_media = transaction.staged_workspace_path(Path("media") / "ad.jpg")
            staged_media.write_bytes(staged_processed.read_bytes())
            transaction.register_processed_artifact(staged_processed, "ad.jpg")
            caption_path, _ = transaction.write_caption("Caption", "ad.txt")
            manifest_path = workspace / "post_manifest.json"
            atomic_write_json(
                manifest_path,
                {
                    "paths": {"caption_path": str(caption_path)},
                    "media_files": [{"filename": "ad.jpg", "relative_path": "temporary", "role": "carousel_item"}],
                },
            )
            transaction.rewrite_manifest_for_final_paths(manifest_path, context.captions_dir / "ad.txt")
            with patch.object(
                transactions,
                "probe_media",
                return_value=SimpleNamespace(actual_type="image", width=1, height=1),
            ):
                transaction.validate(expected_media_count=1)
            result = transaction.commit_and_archive()

            self.assertTrue(result.fully_completed)
            self.assertTrue((result.final_workspace / "post_manifest.json").exists())
            self.assertTrue((context.captions_dir / "ad.txt").exists())
            self.assertTrue((context.processed_dir / "ad.jpg").exists())
            archive = context.inbox_dir / ".archive" / "run-1" / "ad.jpg"
            self.assertEqual(archive.read_bytes(), original_bytes)
            self.assertFalse(source.exists())

    def test_startup_recovery_restores_an_unfinished_precommit_transaction(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            transaction = ProcessingTransaction(context, "run-1", claims, "image_carousel")
            transaction.start("image-carousel-test")

            recovered = recover_incomplete_transactions(context)

            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].action, "restore")
            self.assertTrue(source.exists())
            self.assertFalse(transaction.staging_root.exists())

    def test_postcommit_failure_keeps_workspace_and_recovery_finishes_archive(self) -> None:
        temporary, context, source, claims = self._context_and_claim()
        with temporary:
            def fail_after_commit(checkpoint: str) -> None:
                if checkpoint == "after_commit_before_archive":
                    raise RuntimeError("injected archival interruption")

            transaction = ProcessingTransaction(
                context,
                "run-1",
                claims,
                "image_carousel",
                failure_injector=fail_after_commit,
            )
            workspace, working_sources = transaction.start("image-carousel-test")
            staged_processed = transaction.staged_processed_path("ad.jpg")
            staged_processed.write_bytes(working_sources[0].read_bytes())
            staged_media = transaction.staged_workspace_path(Path("media") / "ad.jpg")
            staged_media.write_bytes(staged_processed.read_bytes())
            transaction.register_processed_artifact(staged_processed, "ad.jpg")
            caption_path, _ = transaction.write_caption("Caption", "ad.txt")
            manifest_path = workspace / "post_manifest.json"
            atomic_write_json(
                manifest_path,
                {
                    "paths": {"caption_path": str(caption_path)},
                    "media_files": [{"filename": "ad.jpg", "relative_path": "temporary", "role": "carousel_item"}],
                },
            )
            transaction.rewrite_manifest_for_final_paths(manifest_path, context.captions_dir / "ad.txt")
            with patch.object(
                transactions,
                "probe_media",
                return_value=SimpleNamespace(actual_type="image", width=1, height=1),
            ):
                transaction.validate(expected_media_count=1)
            result = transaction.commit_and_archive()

            self.assertEqual(result.state, TransactionState.COMMITTED)
            self.assertTrue(result.final_workspace.exists())
            self.assertTrue(claims[0].claimed_path.exists())
            recovered = recover_incomplete_transactions(context)
            self.assertEqual(recovered[0].state, TransactionState.ARCHIVED)
            self.assertTrue((context.inbox_dir / ".archive" / "run-1" / "ad.jpg").exists())

    def test_transactional_video_handler_stages_before_committing_final_output(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        with temporary:
            root = Path(temporary.name)
            context = prepare_app_context(build_app_context(root))
            source = context.inbox_dir / "ad.mp4"
            source.write_bytes(b"original-video")
            claims = claim_inbox_files(context.inbox_dir, [source], "run-1")

            class FakeApi:
                PROMPT_TEMPLATE = "prompt"

                def check_cancelled(self) -> None:
                    return None

                def build_filename_context(self, _paths):
                    return "ad"

                def infer_meta_from_filename(self, _path):
                    return {"brand": "Arcade"}

                def analyze_with_fallback(self, *_args):
                    return (
                        {
                            "title": "Arcade",
                            "description": "A specific arcade ad.",
                            "hashtags": ["arcade"],
                            "notable_details": ["cabinet"],
                            "brand": "Arcade",
                            "decade": "1980s",
                            "year": "1983",
                        },
                        "test",
                        None,
                    )

                def build_caption_payload(self, meta, _name):
                    return {"title": meta["title"], "description": meta["description"], "hashtags": meta["hashtags"], "details": meta["notable_details"]}

                def build_caption_block(self, _meta, _name):
                    return "Caption"

            def fake_convert(_source: Path, destination: Path, **_kwargs) -> bool:
                destination.write_bytes(b"converted-video")
                return True

            transaction = ProcessingTransaction(context, "run-1", claims, "video")
            with (
                patch.object(transactions, "extract_video_frames", return_value=[]),
                patch.object(transactions, "convert_video_to_vertical", side_effect=fake_convert),
                patch.object(transactions.ProcessingTransaction, "preflight_sources", return_value=()),
                patch.object(transactions, "verify_generated_media"),
                patch.object(
                    transactions,
                    "probe_media",
                    return_value=type("Probe", (), {"actual_type": "video", "width": 1080, "height": 1920})(),
                ),
            ):
                result = transactions.process_video_transaction(transaction, FakeApi())

            self.assertEqual(result["status"], "processed")
            self.assertTrue(Path(result["manifest_path"]).exists())
            self.assertTrue((context.inbox_dir / ".archive" / "run-1" / "ad.mp4").exists())
            self.assertFalse(source.exists())


if __name__ == "__main__":
    unittest.main()
