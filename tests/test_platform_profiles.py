from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from platform_profiles import validate_manifest_for_platform  # noqa: E402


class PlatformProfilesTests(unittest.TestCase):
    def test_instagram_video_profile_accepts_vertical_mp4_with_reasonable_caption(self) -> None:
        manifest = {
            "post_type": "video",
            "content": {"description": "A useful caption", "hashtags": ["retro", "ads"]},
            "media_files": [{"filename": "clip.mp4", "width": 1080, "height": 1350}],
        }

        result = validate_manifest_for_platform(manifest, "instagram")

        self.assertTrue(result.ok)
        self.assertEqual(result.platform, "instagram")

    def test_platform_validation_flags_caption_and_media_issues(self) -> None:
        manifest = {
            "post_type": "image_carousel",
            "content": {"description": "x" * 4000, "hashtags": [f"tag{i}" for i in range(40)]},
            "media_files": [{"filename": "ad.bmp", "width": 500, "height": 500} for _ in range(12)],
        }

        result = validate_manifest_for_platform(manifest, "instagram")

        self.assertFalse(result.ok)
        self.assertTrue(any("caption" in issue.lower() for issue in result.issues))
        self.assertTrue(any("hashtag" in issue.lower() for issue in result.issues))
        self.assertTrue(any("carousel" in issue.lower() for issue in result.issues))
        self.assertTrue(any("extension" in issue.lower() for issue in result.issues))

    def test_tiktok_accepts_carousel_video_artifact_when_images_are_present(self) -> None:
        manifest = {
            "post_type": "image_carousel",
            "content": {"description": "A useful caption", "hashtags": ["retro", "ads"]},
            "media_files": [
                {"filename": "scan-one.jpg", "role": "carousel_item", "width": 1080, "height": 1350},
                {"filename": "scan-two.jpg", "role": "carousel_item", "width": 1080, "height": 1350},
                {"filename": "carousel-video.mp4", "role": "carousel_video", "width": 1080, "height": 1350},
            ],
        }

        result = validate_manifest_for_platform(manifest, "tiktok")

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, ())

    def test_instagram_ignores_tiktok_only_carousel_video(self) -> None:
        manifest = {
            "post_type": "image_carousel",
            "content": {"description": "A useful caption", "hashtags": ["retro"]},
            "media_files": [
                {"filename": f"scan-{index}.jpg", "role": "carousel_item", "width": 1080, "height": 1350}
                for index in range(1, 11)
            ]
            + [{"filename": "carousel-video.mp4", "role": "carousel_video", "width": 1080, "height": 1920}],
        }

        result = validate_manifest_for_platform(manifest, "instagram")

        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
