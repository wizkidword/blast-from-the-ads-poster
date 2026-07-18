from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from safe_paths import UnsafePathError, normalize_relative_to, require_plain_filename, resolve_existing_under, resolve_output_under  # noqa: E402
from tests.support import WorkspaceFixture  # noqa: E402


class SafePathTests(unittest.TestCase):
    def test_existing_and_output_paths_stay_structurally_under_root(self) -> None:
        with WorkspaceFixture.create() as workspace:
            source = workspace.write_media(workspace.inbox, "vintage ad.mp4")

            self.assertEqual(resolve_existing_under(workspace.inbox, "vintage ad.mp4"), source.resolve())
            self.assertEqual(
                resolve_output_under(workspace.outputs, "post/media/clip.mp4"),
                workspace.outputs / "post" / "media" / "clip.mp4",
            )

    def test_rejects_traversal_absolute_and_windows_shaped_paths(self) -> None:
        with WorkspaceFixture.create() as workspace:
            outside = workspace.root.parent / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            unsafe_values = (
                "../outside.txt",
                "/outside.txt",
                r"C:\\outside.txt",
                r"C:relative.txt",
                r"\\server\share\file.txt",
                r"\\?\C:\\outside.txt",
            )
            for value in unsafe_values:
                with self.subTest(value=value):
                    with self.assertRaises(UnsafePathError):
                        resolve_output_under(workspace.inbox, value)
                    self.assertTrue(outside.exists())

    def test_legacy_absolute_path_is_accepted_only_inside_approved_root(self) -> None:
        with WorkspaceFixture.create() as workspace:
            inside = workspace.write_media(workspace.inbox, "inside.mp4")
            outside = workspace.root.parent / "legacy-outside.mp4"
            outside.write_bytes(b"outside")

            self.assertEqual(resolve_existing_under(workspace.inbox, inside), inside.resolve())
            self.assertEqual(normalize_relative_to(workspace.inbox, inside), "inside.mp4")
            with self.assertRaises(UnsafePathError):
                resolve_existing_under(workspace.inbox, outside)

    def test_plain_filename_rules_preserve_safe_unicode_and_apostrophes(self) -> None:
        valid = "Mário's very long vintage ad " + ("x" * 160) + ".mp4"
        self.assertEqual(require_plain_filename(valid), valid)
        for value in ("../outside", "nested/name", r"nested\\name", "line\nbreak", "nul\x00name", "stream:ads", r"C:relative"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(UnsafePathError):
                    require_plain_filename(value)

    def test_sibling_prefix_and_symlink_escape_are_rejected(self) -> None:
        with WorkspaceFixture.create() as workspace:
            sibling = workspace.root / "outputs-backup"
            sibling.mkdir()
            outside = sibling / "old.mp4"
            outside.write_bytes(b"outside")
            with self.assertRaises(UnsafePathError):
                resolve_existing_under(workspace.outputs, outside)

            link = workspace.outputs / "escape"
            try:
                os.symlink(sibling, link, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("Symlink creation is unavailable on this runner")
            with self.assertRaises(UnsafePathError):
                resolve_existing_under(workspace.outputs, link / "old.mp4")
            with self.assertRaises(UnsafePathError):
                resolve_output_under(workspace.outputs, link / "new.mp4")

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior only applies on Windows")
    def test_windows_junction_escape_is_rejected_when_junctions_are_available(self) -> None:
        with WorkspaceFixture.create() as workspace:
            outside = workspace.root / "outside"
            outside.mkdir()
            escaped_file = outside / "escaped.mp4"
            escaped_file.write_bytes(b"outside")
            junction = workspace.outputs / "junction"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest("Junction creation is unavailable on this Windows runner")
            try:
                with self.assertRaises(UnsafePathError):
                    resolve_existing_under(workspace.outputs, junction / "escaped.mp4")
            finally:
                junction.rmdir()


if __name__ == "__main__":
    unittest.main()
