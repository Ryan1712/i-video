"""Generate ElevenLabs voice-style samples (for dramatic delivery) and short
music candidate clips (for background-music tone), for the user to pick from.

Usage (from D:\\Video\\agent_video, with .env loaded and ELEVENLABS_API_KEY set):
    py scripts/compare_voice_style_and_music.py

Voice style samples reuse the narrator voice already picked for series 2
(onwK4e9ZLuTAKqWW03F9, "Daniel") at several `style` values.
Music samples are short (30s) previews of a few candidate prompts — the full
~9-minute track is only generated in Task 6, after a prompt is picked.

Output:
    videos/voice_style_compare/style_<value>.mp3
    videos/music_compare/<name>.mp3
Listen to both sets and pick one style value and one music prompt.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent_video.music import generate_music  # noqa: E402
from saas.tts_providers import ElevenLabsTTS  # noqa: E402

SAMPLE_EN = (
    "The first scream came from the apartment upstairs. Then another, and "
    "another, until the whole building seemed to be screaming at once. "
    "Something was moving through the halls, and it was getting closer."
)

VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel, picked in the prior plan's Task 3
VOICE_STYLE_CANDIDATES = [0.0, 0.3, 0.6, 0.9]

MUSIC_PROMPT_CANDIDATES = {
    "dread_drone": (
        "tense atmospheric horror drone, sparse deep bass pulses, building dread, "
        "no melody, no vocals, suitable as quiet background under spoken narration"
    ),
    "heartbeat_tension": (
        "slow ominous heartbeat-like percussion under a thin dissonant string drone, "
        "escalating tension, no melody, no vocals, quiet background under narration"
    ),
}
MUSIC_PREVIEW_DURATION_MS = 30_000

VOICE_OUT_DIR = os.path.join("videos", "voice_style_compare")
MUSIC_OUT_DIR = os.path.join("videos", "music_compare")


def main() -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("Skipping: set ELEVENLABS_API_KEY")
        return

    os.makedirs(VOICE_OUT_DIR, exist_ok=True)
    for style in VOICE_STYLE_CANDIDATES:
        path = os.path.join(VOICE_OUT_DIR, f"style_{style}.mp3")
        print(f"voice style={style} -> {path}")
        ElevenLabsTTS().synthesize(SAMPLE_EN, path, voice=VOICE_ID, language="en", style=style)

    os.makedirs(MUSIC_OUT_DIR, exist_ok=True)
    for name, prompt in MUSIC_PROMPT_CANDIDATES.items():
        path = os.path.join(MUSIC_OUT_DIR, f"{name}.mp3")
        print(f"music '{name}' -> {path}")
        content = generate_music(prompt, MUSIC_PREVIEW_DURATION_MS, api_key)
        with open(path, "wb") as f:
            f.write(content)

    print(f"\nDone. Listen to files in {VOICE_OUT_DIR} and {MUSIC_OUT_DIR}, then pick one of each.")


if __name__ == "__main__":
    main()
