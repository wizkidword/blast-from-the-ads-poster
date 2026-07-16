from __future__ import annotations

from pathlib import Path
from typing import Dict, List

try:
    from ai_analysis import FALLBACK_CAPTION, FALLBACK_CAROUSEL_CAPTION, build_smart_title
except ImportError:
    from scripts.ai_analysis import FALLBACK_CAPTION, FALLBACK_CAROUSEL_CAPTION, build_smart_title


def normalize_hashtags(hashtags: List[str], defaults: List[str], minimum_count: int) -> List[str]:
    cleaned: List[str] = []
    for tag in hashtags:
        normalized = str(tag).strip().lower().replace("#", "").replace(" ", "")
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    for default in defaults:
        if len(cleaned) >= minimum_count:
            break
        if default not in cleaned:
            cleaned.append(default)
    return cleaned


def build_caption_payload(meta: Dict, filename: str) -> Dict:
    hashtags = normalize_hashtags(
        meta.get("hashtags", []),
        ["blastfromtheads", "retroads", "vintageads", "nostalgia", "throwback", "retroculture"],
        minimum_count=10,
    )
    notable_details = meta.get("notable_details") or []
    trimmed_details = [str(item).strip() for item in notable_details if str(item).strip()][:4]
    return {
        "title": build_smart_title(meta, Path(filename)),
        "description": meta.get("description") or FALLBACK_CAPTION,
        "hashtags": hashtags,
        "hashtag_block": " ".join(f"#{tag}" for tag in hashtags),
        "details": trimmed_details,
    }


def build_caption_block(meta: Dict, filename: str) -> str:
    payload = build_caption_payload(meta, filename)
    return f"""{payload["title"]}

{payload["description"]}

{payload["hashtag_block"]}
"""


def build_carousel_caption_payload(meta: Dict) -> Dict:
    hashtags = normalize_hashtags(
        meta.get("hashtags", []),
        [
            "blastfromtheads",
            "carousel",
            "retroads",
            "vintageads",
            "nostalgia",
            "throwback",
            "retroculture",
            "adarchive",
        ],
        minimum_count=12,
    )
    notable_details = meta.get("notable_details") or []
    trimmed_details = [str(item).strip() for item in notable_details if str(item).strip()][:6]
    return {
        "title": build_smart_title(meta, Path("image-carousel-batch.jpg")),
        "description": meta.get("description") or FALLBACK_CAROUSEL_CAPTION,
        "hashtags": hashtags,
        "hashtag_block": " ".join(f"#{tag}" for tag in hashtags),
        "details": trimmed_details,
    }


def build_carousel_caption_block(meta: Dict, image_files: List[Path]) -> str:
    payload = build_carousel_caption_payload(meta)
    return f"""{payload["title"]}

{payload["description"]}

{payload["hashtag_block"]}
"""
