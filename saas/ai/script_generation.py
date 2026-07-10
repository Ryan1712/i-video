"""Generate a full narration script from a brief, sized to a target duration."""
from __future__ import annotations

from .client import AIError, generate_json

# Approximate TTS speaking rates (words per minute) per language.
WORDS_PER_MINUTE = {"vi": 160, "en": 150}
LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def _target_words(target_duration_sec: int, language: str) -> int:
    wpm = WORDS_PER_MINUTE.get(language, 150)
    return max(1, target_duration_sec // 60) * wpm


def generate_script(
    brief: str,
    target_duration_sec: int,
    language: str,
    series_name: str = "",
    series_description: str = "",
) -> str:
    words = _target_words(target_duration_sec, language)
    language_name = LANGUAGE_NAMES.get(language, language)
    system = (
        "You are a professional scriptwriter for narrated YouTube storytelling "
        f"videos. Write in {language_name}. The script is read aloud by a single "
        "narrator: write ONLY the spoken narration — no scene headings, no camera "
        "directions, no speaker labels. Hook the viewer in the first two sentences. "
        'Reply with ONLY a JSON object: {"script": "<full narration>"}'
    )
    user = (
        f"Series: {series_name or '(standalone)'}\n"
        f"Series description: {series_description or '(none)'}\n"
        f"Episode idea/brief (may already be a partial script — expand it):\n{brief}\n\n"
        f"Target length: about {words} words "
        f"(≈{target_duration_sec // 60} minutes of narration)."
    )
    result = generate_json(system, user, max_tokens=16384)
    script = result.get("script")
    if not isinstance(script, str) or not script.strip():
        raise AIError("Model reply missing non-empty 'script' string")
    return script.strip()
