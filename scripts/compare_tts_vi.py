"""Synthesize the same Vietnamese paragraph with every configured TTS voice.

Usage (from D:\\Video\\agent_video, with .env loaded):
    py scripts/compare_tts_vi.py

Configure candidates via env:
    ELEVENLABS_API_KEY + ELEVENLABS_COMPARE_VOICES  (comma-separated voice IDs)
    AZURE_SPEECH_KEY + AZURE_SPEECH_REGION           (voices are preset below)

Output: videos/tts_compare/<provider>_<voice>.mp3 — listen and pick a voice
for the series before producing EP 1.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from saas.tts_providers import AzureTTS, ElevenLabsTTS  # noqa: E402

SAMPLE_VI = (
    "Điều gì sẽ xảy ra nếu một buổi sáng, cả thành phố thức dậy và nhận ra "
    "mạng internet đã biến mất hoàn toàn? Không tin nhắn, không bản đồ, "
    "không một dòng tin tức. Trong ba phút tới, hãy cùng khám phá kịch bản "
    "đáng sợ nhưng hoàn toàn có thể xảy ra này."
)

AZURE_VI_VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]

OUT_DIR = os.path.join("videos", "tts_compare")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    produced = []

    el_voices = [v.strip() for v in os.environ.get("ELEVENLABS_COMPARE_VOICES", "").split(",") if v.strip()]
    if os.environ.get("ELEVENLABS_API_KEY") and el_voices:
        for voice in el_voices:
            path = os.path.join(OUT_DIR, f"elevenlabs_{voice}.mp3")
            print(f"ElevenLabs {voice} -> {path}")
            ElevenLabsTTS().synthesize(SAMPLE_VI, path, voice=voice, language="vi")
            produced.append(path)
    else:
        print("Skipping ElevenLabs (set ELEVENLABS_API_KEY and ELEVENLABS_COMPARE_VOICES)")

    if os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"):
        for voice in AZURE_VI_VOICES:
            path = os.path.join(OUT_DIR, f"azure_{voice}.mp3")
            print(f"Azure {voice} -> {path}")
            AzureTTS().synthesize(SAMPLE_VI, path, voice=voice, language="vi")
            produced.append(path)
    else:
        print("Skipping Azure (set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)")

    print(f"\nDone. {len(produced)} file(s) in {OUT_DIR}. Listen and pick a voice.")


if __name__ == "__main__":
    main()
