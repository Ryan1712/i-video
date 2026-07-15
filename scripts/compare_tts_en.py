"""Synthesize the same English paragraph with several candidate narrator voices.

Usage (from D:\\Video\\agent_video, with .env loaded):
    py scripts/compare_tts_en.py

Configure candidates via env:
    ELEVENLABS_API_KEY + ELEVENLABS_COMPARE_VOICES_EN (comma-separated voice IDs,
        sourced via the shared-voices/voices query in the implementation plan)
    AZURE_SPEECH_KEY + AZURE_SPEECH_REGION           (voices are preset below)

Output: videos/tts_compare_en/<provider>_<voice>.mp3 — listen and pick a voice
for the series.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from saas.tts_providers import AzureTTS, ElevenLabsTTS  # noqa: E402

SAMPLE_EN = (
    "What if, one morning, the entire city woke up to find the internet had "
    "vanished completely? No messages, no maps, not a single line of news. "
    "Over the next three minutes, let's explore this terrifying but entirely "
    "possible scenario."
)

AZURE_EN_VOICES = ["en-US-GuyNeural", "en-US-ChristopherNeural"]

OUT_DIR = os.path.join("videos", "tts_compare_en")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    produced = []

    el_voices = [v.strip() for v in os.environ.get("ELEVENLABS_COMPARE_VOICES_EN", "").split(",") if v.strip()]
    if os.environ.get("ELEVENLABS_API_KEY") and el_voices:
        for voice in el_voices:
            path = os.path.join(OUT_DIR, f"elevenlabs_{voice}.mp3")
            print(f"ElevenLabs {voice} -> {path}")
            ElevenLabsTTS().synthesize(SAMPLE_EN, path, voice=voice, language="en")
            produced.append(path)
    else:
        print("Skipping ElevenLabs (set ELEVENLABS_API_KEY and ELEVENLABS_COMPARE_VOICES_EN)")

    if os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"):
        for voice in AZURE_EN_VOICES:
            path = os.path.join(OUT_DIR, f"azure_{voice}.mp3")
            print(f"Azure {voice} -> {path}")
            AzureTTS().synthesize(SAMPLE_EN, path, voice=voice, language="en")
            produced.append(path)
    else:
        print("Skipping Azure (set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)")

    print(f"\nDone. {len(produced)} file(s) in {OUT_DIR}. Listen and pick a voice.")


if __name__ == "__main__":
    main()
