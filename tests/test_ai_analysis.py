from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ai_analysis  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)
        self.ok = 200 <= status_code < 300

    def json(self) -> dict:
        return self._payload


def sample_meta_json() -> str:
    return json.dumps(
        {
            "title": "1980s Arcade: Neon Cabinet Energy",
            "description": "A specific arcade ad with bright cabinets and action copy.",
            "hashtags": ["arcade", "retroads"],
            "mood": "Electric",
            "decade": "1980s",
            "year": "Unknown",
            "brand": "Arcade",
            "notable_details": ["neon cabinet"],
            "on_screen_text": ["play"],
        }
    )


class OpenAIAnalysisTests(unittest.TestCase):
    def test_prompts_keep_caption_copy_evocative_instead_of_frame_by_frame(self) -> None:
        for prompt in (ai_analysis.PROMPT_TEMPLATE, ai_analysis.IMAGE_CAROUSEL_PROMPT_TEMPLATE):
            self.assertIn("viewer-facing caption copy", prompt)
            self.assertIn("Do not describe the media frame by frame", prompt)
            self.assertIn("Put concrete visual observations in notable_details", prompt)

        self.assertIn("description is the public post caption", ai_analysis.OPENAI_SYSTEM_INSTRUCTIONS)

    def test_call_openai_detailed_sends_images_to_responses_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "ad-frame.jpg"
            image_path.write_bytes(b"fake-image")
            response = FakeResponse(200, {"status": "completed", "output_text": sample_meta_json()})

            with (
                patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}),
                patch.object(ai_analysis, "get_openai_model", return_value="gpt-5.4-nano"),
                patch.object(ai_analysis.requests, "post", return_value=response) as post_mock,
            ):
                meta, error = ai_analysis._call_openai_detailed("Analyze this", [image_path])

            self.assertIsNone(error)
            self.assertEqual(meta["brand"], "Arcade")
            self.assertEqual(post_mock.call_args.args[0], ai_analysis.OPENAI_RESPONSES_URL)
            request_payload = post_mock.call_args.kwargs["json"]
            self.assertEqual(request_payload["model"], "gpt-5.4-nano")
            self.assertEqual(request_payload["input"][0]["content"][0]["type"], "input_text")
            image_part = request_payload["input"][0]["content"][1]
            self.assertEqual(image_part["type"], "input_image")
            self.assertTrue(image_part["image_url"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(request_payload["text"]["format"]["type"], "json_schema")
            self.assertEqual(request_payload["reasoning"], {"effort": "low"})
            self.assertNotIn("temperature", request_payload)
            self.assertFalse(request_payload["store"])

    def test_call_openai_detailed_omits_reasoning_for_non_reasoning_models(self) -> None:
        response = FakeResponse(200, {"status": "completed", "output_text": sample_meta_json()})

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}),
            patch.object(ai_analysis, "get_openai_model", return_value="gpt-4.1"),
            patch.object(ai_analysis.requests, "post", return_value=response) as post_mock,
        ):
            meta, error = ai_analysis._call_openai_detailed("Analyze this", [])

        self.assertIsNone(error)
        self.assertEqual(meta["title"], "1980s Arcade: Neon Cabinet Energy")
        self.assertNotIn("reasoning", post_mock.call_args.kwargs["json"])
        self.assertEqual(post_mock.call_args.kwargs["json"]["temperature"], 0.7)

    def test_call_openai_detailed_reports_missing_key(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            meta, error = ai_analysis._call_openai_detailed("Analyze this", [])

        self.assertIsNone(meta)
        self.assertEqual(error, "OPENAI_API_KEY is not configured")


if __name__ == "__main__":
    unittest.main()
