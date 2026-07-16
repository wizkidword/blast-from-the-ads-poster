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

from thumbnails import ensure_thumbnail, thumbnail_path_for_media  # noqa: E402


class ThumbnailTests(unittest.TestCase):
    def test_thumbnail_path_is_stable_under_workspace_thumbnails_folder(self) -> None:
        workspace = Path("outputs") / "video-abc"
        media = workspace / "media" / "My Clip.mp4"

        path = thumbnail_path_for_media(media, workspace)

        self.assertEqual(path, workspace / "thumbnails" / "my-clip.png")

    def test_ensure_thumbnail_returns_none_when_ffmpeg_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "outputs" / "video-abc"
            media = workspace / "media" / "clip.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"not-real-video")

            with patch("thumbnails.shutil.which", return_value=None):
                result = ensure_thumbnail(media, workspace)

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
