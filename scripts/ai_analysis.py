from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from app_paths import get_project_root
except ImportError:
    from scripts.app_paths import get_project_root

try:
    from media_rules import is_video_file
except ImportError:
    from scripts.media_rules import is_video_file

try:
    from settings_store import load_settings
except ImportError:
    from scripts.settings_store import load_settings

BASE_DIR = get_project_root()
SETTINGS_PATH = BASE_DIR / "settings.json"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_SYSTEM_INSTRUCTIONS = (
    "You are a senior social strategist for a retro ad archive. "
    "Use specific visual evidence, visible text, logos, packaging, character names, and product actions. "
    "The description is the public post caption: make it emotional, nostalgic, and viewer-facing, not a scene log. "
    "Put concrete visual observations in notable_details and visible text in on_screen_text. "
    "Avoid generic captions and vague nostalgia filler."
)
OPENAI_ANALYSIS_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "mood": {"type": "string"},
        "decade": {"type": "string"},
        "year": {"type": "string"},
        "brand": {"type": "string"},
        "notable_details": {"type": "array", "items": {"type": "string"}},
        "on_screen_text": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "description",
        "hashtags",
        "mood",
        "decade",
        "year",
        "brand",
        "notable_details",
        "on_screen_text",
    ],
}

PROMPT_TEMPLATE = """
You are an expert retro advertising copywriter for a nostalgia brand.
Analyze the provided media carefully (image or extracted video frame set) plus filename context.
Return ONLY valid minified JSON with keys:
- title: eye-catching hook (max 80 chars, title case) that SHOULD include year or decade plus brand or product plus a vivid power phrase
- description: 2-4 sentences of viewer-facing caption copy that connects the audience to the feeling of the ad, the era, and the memory it might unlock
- hashtags: array of 14-20 lowercase hashtags WITHOUT # symbols, specific and non-generic
- mood: one or two words
- decade: decade guess like "1980s"
- year: specific year if inferable, else "Unknown"
- brand: company or franchise guess, specific not generic
- notable_details: array of 3-6 short concrete visual details from the media for analysis/reference, not public caption copy
- on_screen_text: array of 0-5 words or short phrases that appear in the frame if legible
Rules:
- Title must NOT be plain filename text.
- Never output placeholders.
- Do not describe the media frame by frame in description.
- Put concrete visual observations in notable_details; use them only to inspire the caption's emotional angle.
- Make description feel like a nostalgic post someone would actually want to read, not an accessibility description or production log.
- If text is visible on packaging, title cards, logos, or ad copy, use it.
- If uncertain, make a best-effort inference from visuals and filename.
- No markdown fences, no prose, JSON only.
""".strip()

IMAGE_CAROUSEL_PROMPT_TEMPLATE = """
You are an expert retro advertising copywriter for a nostalgia brand.
Analyze the PROVIDED IMAGE SET as one cohesive carousel post and use filename hints.
Return ONLY valid minified JSON with keys:
- title: one eye-catching carousel hook (max 80 chars) that SHOULD include year or decade plus brand or product plus vivid phrase
- description: 2-4 sentences of viewer-facing caption copy that makes the carousel feel like a nostalgic discovery from an old magazine, catalog, or archive
- hashtags: array of 14-20 lowercase hashtags WITHOUT # symbols, specific and non-generic
- mood: one or two words
- decade: best overall decade guess like "1980s"
- year: most likely anchor year if inferable, else "Unknown"
- brand: best overall company or franchise guess, specific not generic
- notable_details: array of 4-8 short concrete details that recur across the set for analysis/reference, not public caption copy
- on_screen_text: array of 0-8 words or short phrases visible across the set if legible
Rules:
- Treat all images as one post, not separate posts.
- Do not describe the media frame by frame in description.
- Put concrete visual observations in notable_details; use them only to inspire the caption's emotional angle.
- Make description feel like a nostalgic post someone would actually want to read, not an inventory list.
- Mention this is a carousel only if it feels natural.
- Use specifics from the art, logos, price bursts, taglines, and product categories to shape the feeling, not to list every item.
- No markdown fences, no prose, JSON only.
""".strip()

FALLBACK_CAPTION = (
    "A throwback ad drop from the vault and the nostalgia levels are maxed. "
    "Spot the era details and tell us what memory this unlocks for you."
)
FALLBACK_CAROUSEL_CAPTION = (
    "Swipe through this retro ad carousel and soak in the era-defining design energy. "
    "From bold print vibes to classic brand nostalgia, this set is pure time-capsule fuel. "
    "Which frame hits you with the strongest memory?"
)

VIDEO_HOOK_PATTERNS = [
    "{time_part} {subject}: Time-Capsule TV Gold",
    "{time_part} {subject}: Saturday Morning Energy",
    "{time_part} {subject}: Commercial Break Classic",
    "{time_part} {subject}: Retro Screen-Time Magic",
    "{time_part} {subject}: Pure Throwback Hype",
    "{time_part} {subject}: Vintage Airwaves Hit",
]

IMAGE_HOOK_PATTERNS = [
    "{time_part} {subject}: Collector-Grade Throwback",
    "{time_part} {subject}: Print-Ad Time Machine",
    "{time_part} {subject}: Retro Design Gold",
    "{time_part} {subject}: Archive-Worthy Classic",
    "{time_part} {subject}: Nostalgia Shelf Gem",
    "{time_part} {subject}: Era-Defining Ad Art",
]


def get_openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    settings = load_settings(SETTINGS_PATH)
    return os.environ.get("OPENAI_API_MODEL", settings.openai_model).strip() or settings.openai_model


def get_allow_generic_fallback() -> bool:
    value = os.environ.get("ALLOW_GENERIC_FALLBACK_CAPTIONS", "").strip().lower()
    if value:
        return value in {"1", "true", "yes", "on"}
    return load_settings(SETTINGS_PATH).allow_generic_fallback_captions


def extract_json_object(text: str) -> Optional[Dict]:
    if not text:
        return None
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return None

    return parsed if isinstance(parsed, dict) else None


def build_filename_context(file_paths: List[Path]) -> str:
    normalized = [path.stem.replace("_", " ").replace("-", " ").strip() for path in file_paths]
    return "; ".join(part for part in normalized if part)


def pick_representative_files(file_paths: List[Path], limit: int) -> List[Path]:
    if len(file_paths) <= limit:
        return list(file_paths)
    if limit <= 1:
        return [file_paths[0]]

    step = (len(file_paths) - 1) / (limit - 1)
    indices = []
    for index in range(limit):
        candidate = round(index * step)
        if candidate not in indices:
            indices.append(candidate)

    for index in range(len(file_paths)):
        if len(indices) >= limit:
            break
        if index not in indices:
            indices.append(index)

    return [file_paths[index] for index in sorted(indices[:limit])]


def build_smart_title(meta: Dict, file_path: Path) -> str:
    current = str(meta.get("title") or "").strip()
    stem_title = file_path.stem.replace("_", " ").replace("-", " ").title()
    year = str(meta.get("year") or "Unknown")
    decade = str(meta.get("decade") or "Unknown")
    brand = str(meta.get("brand") or "Unknown")

    has_time = (year != "Unknown" and year in current) or (decade != "Unknown" and decade in current)
    has_brand = brand != "Unknown" and brand.lower() in current.lower()
    too_filename_like = current.lower() == stem_title.lower()

    if current and has_time and has_brand and not too_filename_like:
        return current

    subject = brand if brand != "Unknown" else stem_title
    time_part = year if year != "Unknown" else (decade if decade != "Unknown" else "Retro Era")
    patterns = VIDEO_HOOK_PATTERNS if is_video_file(file_path) else IMAGE_HOOK_PATTERNS
    stable_key = f"{file_path.stem.lower()}::{time_part.lower()}::{subject.lower()}"
    index = int(hashlib.md5(stable_key.encode("utf-8")).hexdigest(), 16) % len(patterns)
    return patterns[index].format(time_part=time_part, subject=subject)


def infer_meta_from_filename(file_path: Path) -> Dict:
    stem = file_path.stem
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", stem)
    year = year_match.group(1) if year_match else "Unknown"
    decade = f"{year[:3]}0s" if year != "Unknown" else "Unknown"

    known_brands = [
        "nintendo",
        "sega",
        "atari",
        "capcom",
        "konami",
        "hasbro",
        "mattel",
        "game informer",
        "funco",
        "micro machines",
        "gi joe",
        "thundercats",
        "transformers",
        "tmnt",
    ]
    lower = stem.lower().replace("_", " ")
    brand = "Unknown"
    for candidate in known_brands:
        if candidate in lower:
            brand = candidate.title()
            break

    hashtags = ["blastfromtheads", "retroads", "vintageads", "nostalgia", "throwback"]
    if decade != "Unknown":
        hashtags.append(decade.lower())
    if year != "Unknown":
        hashtags.append(year.lower())
    if brand != "Unknown":
        hashtags.append(brand.lower().replace(" ", ""))

    return {
        "title": stem.replace("_", " ").replace("-", " ").title(),
        "description": FALLBACK_CAPTION,
        "hashtags": hashtags[:12],
        "brand": brand,
        "decade": decade,
        "year": year,
        "mood": "Nostalgic",
    }


def infer_carousel_meta_from_files(image_files: List[Path]) -> Dict:
    inferred = [infer_meta_from_filename(path) for path in image_files]
    years = [item["year"] for item in inferred if item.get("year") != "Unknown"]
    decades = [item["decade"] for item in inferred if item.get("decade") != "Unknown"]
    brands = [item["brand"] for item in inferred if item.get("brand") != "Unknown"]

    brand = max(set(brands), key=brands.count) if brands else "Unknown"
    decade = max(set(decades), key=decades.count) if decades else "Unknown"
    year = years[0] if years else "Unknown"
    title = "Retro Ad Carousel: Collector-Grade Throwback"
    if brand != "Unknown" and decade != "Unknown":
        title = f"{decade} {brand}: Carousel Throwback Gold"
    elif decade != "Unknown":
        title = f"{decade} Retro Ads: Carousel Throwback Gold"

    hashtags = [
        "blastfromtheads",
        "carousel",
        "retroads",
        "vintageads",
        "nostalgia",
        "throwback",
        "retrocollectibles",
        "adarchive",
        "retroculture",
        "timemachine",
    ]
    for item in inferred:
        for tag in item.get("hashtags", []):
            cleaned = str(tag).strip().lower().replace("#", "").replace(" ", "")
            if cleaned and cleaned not in hashtags:
                hashtags.append(cleaned)
            if len(hashtags) >= 18:
                break
        if len(hashtags) >= 18:
            break

    return {
        "title": title,
        "description": FALLBACK_CAROUSEL_CAPTION,
        "hashtags": hashtags[:18],
        "brand": brand,
        "decade": decade,
        "year": year,
        "mood": "Nostalgic",
    }


def _build_openai_content(prompt: str, file_paths: List[Path]) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    for file_path in file_paths:
        if not file_path.exists():
            continue
        mime = mimetypes.guess_type(file_path.name)[0] or "image/jpeg"
        data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{data}",
                "detail": "high",
            }
        )
    return content


def _extract_openai_output_text(payload: Dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts: List[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _supports_reasoning(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith("gpt-5") or normalized.startswith("o")


def _call_openai_detailed(prompt: str, file_paths: List[Path]) -> Tuple[Optional[Dict], Optional[str]]:
    api_key = get_openai_api_key()
    if not api_key:
        return None, "OPENAI_API_KEY is not configured"

    model = get_openai_model()
    payload: Dict[str, Any] = {
        "model": model,
        "instructions": OPENAI_SYSTEM_INSTRUCTIONS,
        "input": [
            {
                "role": "user",
                "content": _build_openai_content(prompt, file_paths),
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "retro_ad_analysis",
                "schema": OPENAI_ANALYSIS_JSON_SCHEMA,
                "strict": True,
            },
            "verbosity": "medium",
        },
        "max_output_tokens": 1400,
        "store": False,
    }
    if _supports_reasoning(model):
        payload["reasoning"] = {"effort": "low"}
    else:
        payload["temperature"] = 0.7
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Optional[str] = None
    for attempt in range(1, 6):
        try:
            response = requests.post(OPENAI_RESPONSES_URL, headers=headers, json=payload, timeout=180)
        except requests.RequestException as exc:
            last_error = f"request error on attempt {attempt}: {exc}"
            if attempt < 5:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
                continue
            return None, last_error

        if response.status_code in {408, 409, 429, 500, 502, 503, 504}:
            last_error = f"OpenAI {response.status_code} on attempt {attempt}: {response.text[:300]}"
            if attempt < 5:
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
                continue
            return None, last_error

        if not response.ok:
            return None, f"OpenAI {response.status_code}: {response.text[:500]}"

        try:
            response_payload = response.json()
        except ValueError:
            return None, f"OpenAI returned non-JSON response: {response.text[:500]}"

        if response_payload.get("error"):
            return None, f"OpenAI response error: {json.dumps(response_payload.get('error'))[:500]}"

        if response_payload.get("status") == "incomplete":
            return None, f"OpenAI response incomplete: {json.dumps(response_payload.get('incomplete_details'))[:500]}"

        text = _extract_openai_output_text(response_payload)
        parsed = extract_json_object(text)
        if parsed is None:
            return None, f"OpenAI returned non-JSON or unparsable JSON: {text[:500]}"
        return parsed, None

    return None, last_error or "Unknown OpenAI error"


def _call_openai(prompt: str, file_paths: List[Path]) -> Optional[Dict]:
    result, _ = _call_openai_detailed(prompt, file_paths)
    return result


def analyze_with_fallback(prompt: str, file_paths: List[Path], fallback_meta: Dict) -> Tuple[Optional[Dict], str, Optional[str]]:
    vision_meta, vision_error = _call_openai_detailed(prompt, file_paths) if file_paths else (None, "No files were provided for vision analysis")
    if vision_meta:
        return vision_meta, "openai_vision", None

    text_only_meta, text_error = _call_openai_detailed(prompt, [])
    if text_only_meta:
        return text_only_meta, "openai_text_only", None

    if get_allow_generic_fallback():
        combined_error = f"Vision failed: {vision_error}. Text-only failed: {text_error}. Using generic fallback because ALLOW_GENERIC_FALLBACK_CAPTIONS is enabled."
        return fallback_meta, "fallback", combined_error

    combined_error = f"Vision failed: {vision_error}. Text-only failed: {text_error}."
    return None, "failed", combined_error


def analyze_image_batch_with_fallback(prompt: str, image_files: List[Path], fallback_meta: Dict) -> Tuple[Optional[Dict], str, Optional[str]]:
    full_meta, full_error = _call_openai_detailed(prompt, image_files) if image_files else (None, "No files were provided for vision analysis")
    if full_meta:
        return full_meta, "openai_vision", None

    subset_attempts: List[Tuple[int, List[Path]]] = []
    for limit in (6, 4, 3):
        if len(image_files) > limit:
            subset_attempts.append((limit, pick_representative_files(image_files, limit)))

    subset_errors: List[str] = []
    for limit, subset_files in subset_attempts:
        subset_names = ", ".join(path.name for path in subset_files)
        subset_prompt = (
            f"{prompt}\n"
            f"IMPORTANT: The attached files are a representative subset of a larger carousel batch ({len(image_files)} total images). "
            f"Use the full filename list already provided plus this subset ({subset_names}) to infer the best unified caption for the whole carousel."
        )
        subset_meta, subset_error = _call_openai_detailed(subset_prompt, subset_files)
        if subset_meta:
            return subset_meta, f"openai_vision_subset_{limit}", full_error
        subset_errors.append(f"subset_{limit} failed: {subset_error}")

    text_only_meta, text_error = _call_openai_detailed(prompt, [])
    if text_only_meta:
        return text_only_meta, "openai_text_only", None

    if get_allow_generic_fallback():
        combined_error = (
            f"Vision failed: {full_error}. "
            f"{' '.join(subset_errors)} "
            f"Text-only failed: {text_error}. Using generic fallback because ALLOW_GENERIC_FALLBACK_CAPTIONS is enabled."
        ).strip()
        return fallback_meta, "fallback", combined_error

    combined_error = (
        f"Vision failed: {full_error}. "
        f"{' '.join(subset_errors)} "
        f"Text-only failed: {text_error}."
    ).strip()
    return None, "failed", combined_error


def call_openai(prompt: str, file_path: Optional[Path] = None) -> Optional[Dict]:
    files = [file_path] if file_path else []
    return _call_openai(prompt, [path for path in files if path is not None])


def call_openai_with_files(prompt: str, file_paths: List[Path]) -> Optional[Dict]:
    return _call_openai(prompt, file_paths)


# Compatibility aliases for older scripts/tests that imported the Gemini names.
get_google_api_key = get_openai_api_key
get_google_model = get_openai_model
_call_gemini_detailed = _call_openai_detailed
_call_gemini = _call_openai
call_gemini = call_openai
call_gemini_with_files = call_openai_with_files
