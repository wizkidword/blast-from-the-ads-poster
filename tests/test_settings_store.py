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

from settings_store import AppSettings, load_settings, resolve_configured_dir, save_settings  # noqa: E402


class SettingsStoreTests(unittest.TestCase):
    def test_load_settings_returns_defaults_when_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(Path(temp_dir) / "settings.json")

            self.assertEqual(settings.openai_model, "gpt-5.4-nano")
            self.assertFalse(settings.allow_generic_fallback_captions)
            self.assertEqual(settings.default_providers, ("manual_export",))
            self.assertEqual(settings.logs_retention_days, 90)
            self.assertEqual(settings.captions_dir, "")
            self.assertEqual(settings.processed_dir, "")

    def test_settings_round_trip_preserves_non_secret_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = AppSettings(
                openai_model="gpt-5.4",
                allow_generic_fallback_captions=True,
                default_providers=("manual_export", "instagram"),
                logs_retention_days=30,
                posting_pack_retention_days=10,
                orphan_output_retention_days=5,
                captions_dir=r"H:\Postiz\Captions",
                processed_dir=r"H:\Postiz\Processed",
            )

            save_settings(settings_path, settings)
            loaded = load_settings(settings_path)

            self.assertEqual(loaded, settings)
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertNotIn("GOOGLE_API_KEY", json.dumps(raw))
            self.assertNotIn("OPENAI_API_KEY", json.dumps(raw))
            self.assertEqual(raw["captions_dir"], r"H:\Postiz\Captions")
            self.assertEqual(raw["processed_dir"], r"H:\Postiz\Processed")

    def test_load_settings_ignores_legacy_gemini_model_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text(json.dumps({"gemini_model": "gemini-2.5-flash"}), encoding="utf-8")

            settings = load_settings(settings_path)

            self.assertEqual(settings.openai_model, "gpt-5.4-nano")

    def test_resolve_configured_dir_supports_default_relative_and_absolute_paths(self) -> None:
        base_dir = Path(r"C:\Project")

        self.assertEqual(resolve_configured_dir(base_dir, "", "captions"), base_dir / "captions")
        self.assertEqual(resolve_configured_dir(base_dir, "exports/captions", "captions"), base_dir / "exports/captions")
        self.assertEqual(resolve_configured_dir(base_dir, r"H:\Postiz\Captions", "captions"), Path(r"H:\Postiz\Captions"))


if __name__ == "__main__":
    unittest.main()
