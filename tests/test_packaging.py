from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_standalone_build_does_not_copy_real_env_file(self) -> None:
        build_script = (ROOT / "Build-Standalone-Exe.bat").read_text(encoding="utf-8")

        self.assertIn('.env.example', build_script)
        self.assertNotIn('copy /Y ".env"', build_script)

    def test_standalone_build_includes_run_history_module(self) -> None:
        build_script = (ROOT / "Build-Standalone-Exe.bat").read_text(encoding="utf-8")

        self.assertIn('--hidden-import "run_history"', build_script)

    def test_standalone_build_includes_v2_helper_modules(self) -> None:
        build_script = (ROOT / "Build-Standalone-Exe.bat").read_text(encoding="utf-8")

        for module_name in (
            "ai_analysis",
            "app_metadata",
            "caption_builder",
            "cancellable_subprocess",
            "cleanup",
            "desktop_requeue",
            "desktop_review",
            "desktop_settings",
            "desktop_status",
            "desktop_theme",
            "desktop_workflow",
            "export_packs",
            "manifest_service",
            "media_artifacts",
            "media_processing",
            "platform_profiles",
            "processing_orchestrator",
            "processing_transaction",
            "recovery_queue",
            "recovery_service",
            "review_queue",
            "run_ledger",
            "settings_store",
            "thumbnails",
            "workspace_lock",
        ):
            self.assertIn(f'--hidden-import "{module_name}"', build_script)

    def test_app_metadata_declares_version(self) -> None:
        import sys

        scripts_dir = ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        from app_metadata import APP_VERSION, build_version_label  # noqa: E402

        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertIn(APP_VERSION, build_version_label())

    def test_release_verification_script_runs_expected_checks(self) -> None:
        script = (ROOT / "Verify-Release.bat").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover -s tests -v", script)
        self.assertIn("python -m compileall -q scripts tests", script)
        self.assertIn("python scripts\\workflow.py setup", script)
        self.assertIn("Build-Standalone-Exe.bat", script)


if __name__ == "__main__":
    unittest.main()
