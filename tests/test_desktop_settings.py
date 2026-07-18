from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_settings import SettingsFormState, build_settings_form_state, parse_settings_form_state  # noqa: E402
from settings_store import AppSettings  # noqa: E402


class DesktopSettingsTests(unittest.TestCase):
    def test_build_settings_form_state_converts_settings_to_editable_strings(self) -> None:
        state = build_settings_form_state(
            AppSettings(
                openai_model="gpt-test",
                allow_generic_fallback_captions=True,
                default_providers=("manual_export", "instagram"),
                logs_retention_days=120,
                posting_pack_retention_days=45,
                orphan_output_retention_days=21,
                stale_draft_days=14,
                preferred_platforms=("manual_export", "facebook"),
                captions_dir=r"H:\Postiz\Captions",
                processed_dir=r"H:\Postiz\Processed",
                max_media_file_bytes=123,
                max_image_pixels=456,
                max_image_dimension=789,
                max_video_duration_seconds=90,
                max_carousel_images=4,
                max_analysis_payload_bytes=321,
            )
        )

        self.assertEqual(state.openai_model, "gpt-test")
        self.assertTrue(state.allow_generic_fallback_captions)
        self.assertEqual(state.default_providers, "manual_export, instagram")
        self.assertEqual(state.logs_retention_days, "120")
        self.assertEqual(state.preferred_platforms, "manual_export, facebook")
        self.assertEqual(state.captions_dir, r"H:\Postiz\Captions")
        self.assertEqual(state.processed_dir, r"H:\Postiz\Processed")
        self.assertEqual(state.max_video_duration_seconds, "90")

    def test_parse_settings_form_state_returns_validated_app_settings(self) -> None:
        settings = parse_settings_form_state(
            SettingsFormState(
                openai_model=" gpt-5.4-nano ",
                allow_generic_fallback_captions=False,
                default_providers="manual_export, instagram",
                logs_retention_days="90",
                posting_pack_retention_days="30",
                orphan_output_retention_days="14",
                stale_draft_days="10",
                preferred_platforms="manual_export, instagram, facebook",
                captions_dir=r" H:\Postiz\Captions ",
                processed_dir=r" H:\Postiz\Processed ",
                max_media_file_bytes="123",
                max_image_pixels="456",
                max_image_dimension="789",
                max_video_duration_seconds="90",
                max_carousel_images="4",
                max_analysis_payload_bytes="321",
            )
        )

        self.assertEqual(settings.openai_model, "gpt-5.4-nano")
        self.assertEqual(settings.default_providers, ("manual_export", "instagram"))
        self.assertEqual(settings.logs_retention_days, 90)
        self.assertEqual(settings.preferred_platforms, ("manual_export", "instagram", "facebook"))
        self.assertEqual(settings.captions_dir, r"H:\Postiz\Captions")
        self.assertEqual(settings.processed_dir, r"H:\Postiz\Processed")
        self.assertEqual(settings.max_analysis_payload_bytes, 321)

    def test_parse_settings_form_state_rejects_non_positive_retention_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "logs_retention_days"):
            parse_settings_form_state(
                SettingsFormState(
                    openai_model="gpt-5.4-nano",
                    allow_generic_fallback_captions=False,
                    default_providers="manual_export",
                    logs_retention_days="0",
                    posting_pack_retention_days="30",
                    orphan_output_retention_days="14",
                    stale_draft_days="10",
                    preferred_platforms="manual_export",
                    captions_dir="",
                    processed_dir="",
                )
            )


if __name__ == "__main__":
    unittest.main()
