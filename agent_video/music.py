"""ElevenLabs Music API client for generating a whole-episode background track."""
from __future__ import annotations

import requests

ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music"

MUSIC_MIN_DURATION_MS = 3_000
MUSIC_MAX_DURATION_MS = 600_000


class MusicError(RuntimeError):
    pass


def generate_music(prompt: str, duration_ms: int, api_key: str) -> bytes:
    if not api_key:
        raise MusicError("ELEVENLABS_API_KEY not set")
    if not MUSIC_MIN_DURATION_MS <= duration_ms <= MUSIC_MAX_DURATION_MS:
        raise MusicError(
            f"duration_ms must be between {MUSIC_MIN_DURATION_MS} and "
            f"{MUSIC_MAX_DURATION_MS}, got {duration_ms}"
        )

    try:
        resp = requests.post(
            ELEVENLABS_MUSIC_URL,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"prompt": prompt, "music_length_ms": duration_ms, "force_instrumental": True},
            timeout=300,
        )
    except requests.exceptions.RequestException as exc:
        raise MusicError(f"ElevenLabs Music request failed: {exc}") from exc

    if resp.status_code != 200:
        raise MusicError(f"ElevenLabs Music failed ({resp.status_code}): {resp.text[:500]}")

    return resp.content
