from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app_context import build_app_context  # noqa: E402
from app_metadata import PACKAGE_HIDDEN_IMPORTS, SUPPORTED_PYTHON_VERSION, build_version_label  # noqa: E402
from release_artifacts import parse_locked_packages, write_release_metadata  # noqa: E402
from repo_hygiene import inspect_tracked_file  # noqa: E402
from social_batch_app import run_packaged_smoke_test  # noqa: E402


class PackagingTests(unittest.TestCase):
    def test_standalone_build_uses_the_shared_setup_and_never_copies_local_configuration(self) -> None:
        build_script = (ROOT / "Build-Standalone-Exe.bat").read_text(encoding="utf-8")

        self.assertIn("Setup-Environment.bat", build_script)
        self.assertIn('"%BLAST_PYTHON%" -m PyInstaller', build_script)
        self.assertIn("release_artifacts.py", build_script)
        self.assertIn('.env.example', build_script)
        self.assertIn("settings.example.json", build_script)
        self.assertNotIn('copy /Y ".env"', build_script)
        self.assertNotIn('copy /Y "settings.json"', build_script)

    def test_spec_uses_the_shared_hidden_import_list_without_machine_paths(self) -> None:
        spec = (ROOT / "BlastFromTheAds.spec").read_text(encoding="utf-8")

        self.assertIn("PACKAGE_HIDDEN_IMPORTS", spec)
        self.assertIn("Path(SPECPATH).resolve()", spec)
        self.assertNotIn("C:\\Users\\", spec)
        self.assertIn("media_probe", PACKAGE_HIDDEN_IMPORTS)
        self.assertIn("processing_transaction", PACKAGE_HIDDEN_IMPORTS)

    def test_lock_is_hashed_and_pins_runtime_and_build_dependencies(self) -> None:
        packages = dict(parse_locked_packages(ROOT / "requirements-windows-py313.txt"))

        self.assertEqual(packages["requests"], "2.33.1")
        self.assertEqual(packages["pyinstaller"], "6.20.0")
        self.assertEqual(SUPPORTED_PYTHON_VERSION, (3, 13))
        self.assertIn("requirements-windows-py313.txt", (ROOT / "requirements.txt").read_text(encoding="utf-8"))

    def test_release_verification_uses_the_same_virtual_environment(self) -> None:
        for name in ("Setup-Environment.bat", "Build-Standalone-Exe.bat", "Verify-Release.bat", "Launch-Blast-From-The-Ads.bat"):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("Setup-Environment.bat", script) if name != "Setup-Environment.bat" else self.assertIn("py -3.13", script)
        verify_script = (ROOT / "Verify-Release.bat").read_text(encoding="utf-8")
        self.assertIn('"%BLAST_PYTHON%" -m unittest discover -s tests -v', verify_script)
        self.assertIn('"%BLAST_PYTHON%" -m compileall -q scripts tests', verify_script)
        self.assertIn('BlastFromTheAds.exe" --smoke-test', verify_script)

    def test_settings_example_is_generic_and_local_settings_are_ignored(self) -> None:
        settings = json.loads((ROOT / "settings.example.json").read_text(encoding="utf-8"))
        ignore_rules = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertEqual(settings["schema_version"], 4)
        self.assertEqual(settings["captions_dir"], "")
        self.assertEqual(settings["processed_dir"], "")
        self.assertIn("settings.json", ignore_rules)
        self.assertIn("/inbox/*", ignore_rules)
        self.assertIn("/exports/*", ignore_rules)

    def test_packaged_smoke_test_imports_modules_without_starting_tk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = build_app_context(Path(temp_dir))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_packaged_smoke_test(context), 0)

            self.assertTrue(context.inbox_dir.is_dir())
            self.assertTrue(context.outputs_dir.is_dir())
            self.assertIn("Blast From the Ads", build_version_label())

    def test_release_metadata_contains_hashes_and_spdx_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "dist"
            (artifact_root / "package").mkdir(parents=True)
            (artifact_root / "BlastFromTheAds.exe").write_bytes(b"executable")
            (artifact_root / "package" / "README.md").write_text("release", encoding="utf-8")

            checksums_path, sbom_path = write_release_metadata(
                artifact_root,
                artifact_root / "release-metadata",
                [{"name": "example-package", "version": "1.0.0", "license": "MIT"}],
            )

            self.assertEqual(len(checksums_path.read_text(encoding="utf-8").splitlines()), 2)
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
            self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
            self.assertEqual(sbom["packages"][0]["name"], "example-package")
            self.assertEqual(len(sbom["files"]), 2)

    def test_hygiene_check_rejects_tracked_local_config_secrets_and_large_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps({"api" + "_key": "demo-" + "credential"}), encoding="utf-8")
            errors = inspect_tracked_file(root, Path("settings.json"), max_file_bytes=10)

            self.assertTrue(any("local configuration" in error for error in errors))
            self.assertTrue(any("Possible secret" in error for error in errors))
            self.assertTrue(any("exceeds" in error for error in errors))
            self.assertFalse(any("demo-credential" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
