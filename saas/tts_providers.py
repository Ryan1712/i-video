"""TTS behind a provider interface: ElevenLabs (wraps the engine) and Azure Speech."""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

import requests

from agent_video.tts import TTSError, synthesize_scene

AZURE_TTS_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


class ElevenLabsTTS:
    def synthesize(self, text: str, out_path: str, voice: str, language: str, style: float = 0.0) -> None:
        synthesize_scene(
            text,
            out_path,
            os.environ.get("ELEVENLABS_API_KEY", ""),
            voice or os.environ.get("ELEVENLABS_VOICE_ID", ""),
            style=style,
        )


class AzureTTS:
    def synthesize(self, text: str, out_path: str, voice: str, language: str, style: float = 0.0) -> None:
        # style is an ElevenLabs-only expressiveness knob; Azure has no equivalent, so it's accepted and ignored
        # to keep the interface uniform for saas/tasks.py.
        key = os.environ.get("AZURE_SPEECH_KEY", "")
        region = os.environ.get("AZURE_SPEECH_REGION", "")
        if not key or not region:
            raise TTSError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set")
        lang_tag = {"vi": "vi-VN", "en": "en-US"}.get(language, "en-US")
        voice_attr = escape(voice, {"'": "&apos;"})
        ssml = (
            f"<speak version='1.0' xml:lang='{lang_tag}'>"
            f"<voice name='{voice_attr}'>{escape(text)}</voice></speak>"
        )
        response = requests.post(
            AZURE_TTS_URL.format(region=region),
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            },
            data=ssml.encode("utf-8"),
            timeout=120,
        )
        if response.status_code != 200:
            raise TTSError(f"Azure TTS failed ({response.status_code}): {response.text[:500]}")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(response.content)


def get_tts_provider(name: str | None = None):
    resolved = name or os.environ.get("TTS_PROVIDER", "elevenlabs")
    if resolved == "elevenlabs":
        return ElevenLabsTTS()
    if resolved == "azure":
        return AzureTTS()
    raise ValueError(f"Unknown TTS provider: {resolved}")
