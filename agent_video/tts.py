"""ElevenLabs text-to-speech for each scene."""
from __future__ import annotations

import json
import os
import subprocess

import requests
from imageio_ffmpeg import get_ffmpeg_exe

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class TTSError(RuntimeError):
    pass


def synthesize_scene(text: str, out_path: str, api_key: str, voice_id: str) -> None:
    if not api_key or not voice_id:
        raise TTSError(
            "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set. See SETUP.md."
        )

    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    resp = requests.post(
        url,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise TTSError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:500]}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(resp.content)


def get_audio_duration(path: str) -> float:
    ffmpeg_exe = get_ffmpeg_exe()
    ffprobe_exe = ffmpeg_exe.replace("ffmpeg", "ffprobe")
    if not os.path.isfile(ffprobe_exe):
        # imageio-ffmpeg only ships ffmpeg; use ffmpeg itself to get duration instead.
        result = subprocess.run(
            [ffmpeg_exe, "-i", path, "-f", "null", "-"],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        for line in result.stderr.splitlines():
            line = line.strip()
            if line.startswith("Duration:"):
                # Duration: 00:00:03.45, start: ...
                ts = line.split(",")[0].split("Duration:")[1].strip()
                h, m, s = ts.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
        raise TTSError(f"Could not determine duration of {path}")

    result = subprocess.run(
        [
            ffprobe_exe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
