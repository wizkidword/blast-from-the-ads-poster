from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from atomic_io import atomic_write_text  # noqa: E402


class AtomicIOTests(unittest.TestCase):
    def test_failed_replace_preserves_existing_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            path.write_text("known-good", encoding="utf-8")

            with patch("atomic_io.os.replace", side_effect=OSError("simulated replacement failure")):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new value")

            self.assertEqual(path.read_text(encoding="utf-8"), "known-good")
            self.assertEqual(list(path.parent.glob(".settings.json.*.tmp")), [])

    def test_failed_replace_cleans_only_its_own_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            preserved_temp = path.parent / ".settings.json.preexisting.tmp"
            preserved_temp.write_text("keep for inspection", encoding="utf-8")

            with patch("atomic_io.os.replace", side_effect=OSError("simulated replacement failure")):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "new value")

            self.assertEqual(preserved_temp.read_text(encoding="utf-8"), "keep for inspection")
            self.assertEqual(list(path.parent.glob(".settings.json.*.tmp")), [preserved_temp])


if __name__ == "__main__":
    unittest.main()
