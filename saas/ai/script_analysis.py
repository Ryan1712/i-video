"""Split a narration script into scenes and match each to a series asset."""
from __future__ import annotations

import json

from .client import AIError, generate_json

LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def analyze_script(script: str, language: str, asset_catalog: list[dict]) -> list[dict]:
    language_name = LANGUAGE_NAMES.get(language, language)
    catalog_json = json.dumps(asset_catalog, ensure_ascii=False, indent=1)
    system = (
        "You split a narrated YouTube video script into visual scenes. "
        "Each scene is 1-4 sentences of narration shown over ONE still image. "
        f"The narration language is {language_name}.\n"
        f"Available images (the series asset catalog):\n{catalog_json}\n\n"
        "For each scene pick the best-matching asset id from the catalog, or null "
        "if none fits. When asset_id is null, write asset_brief: a detailed, "
        "self-contained ENGLISH image-generation prompt for the missing image "
        "(subject, setting, mood, composition). Keep the narration text verbatim — "
        "do not rewrite it, only split it.\n"
        'Reply with ONLY JSON: {"scenes": [{"narration_text": str, '
        '"asset_id": int | null, "asset_brief": str | null}]}'
    )
    result = generate_json(system, f"Script:\n{script}", max_tokens=16384)

    raw_scenes = result.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise AIError("Model reply missing non-empty 'scenes' list")

    valid_ids = {a["id"] for a in asset_catalog}
    scenes: list[dict] = []
    for raw in raw_scenes:
        narration = raw.get("narration_text")
        if not isinstance(narration, str) or not narration.strip():
            raise AIError("Scene missing narration_text")
        asset_id = raw.get("asset_id")
        brief = raw.get("asset_brief")
        if asset_id not in valid_ids:
            asset_id = None
        if asset_id is None and (not isinstance(brief, str) or not brief.strip()):
            brief = f"Illustration for: {narration.strip()[:200]}"
        scenes.append(
            {
                "narration_text": narration.strip(),
                "asset_id": asset_id,
                "asset_brief": brief.strip() if (asset_id is None and brief) else None,
            }
        )
    return scenes
