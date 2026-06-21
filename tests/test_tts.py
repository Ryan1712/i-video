import json
from unittest.mock import patch, MagicMock

import pytest

from agent_video.tts import synthesize_scene, get_audio_duration, TTSError


def test_synthesize_scene_raises_without_credentials(tmp_path):
    out_path = str(tmp_path / "scene_01.mp3")

    with pytest.raises(TTSError, match="ELEVENLABS_API_KEY"):
        synthesize_scene("hello", out_path, api_key="", voice_id="")


def test_synthesize_scene_writes_audio_bytes_on_success(tmp_path):
    out_path = str(tmp_path / "audio" / "scene_01.mp3")
    fake_resp = MagicMock(status_code=200, content=b"fake-mp3-bytes")

    with patch("agent_video.tts.requests.post", return_value=fake_resp) as post_mock:
        synthesize_scene("hello", out_path, api_key="key123", voice_id="voiceABC")

    assert post_mock.call_args[0][0] == "https://api.elevenlabs.io/v1/text-to-speech/voiceABC"
    assert post_mock.call_args[1]["headers"]["xi-api-key"] == "key123"
    with open(out_path, "rb") as f:
        assert f.read() == b"fake-mp3-bytes"


def test_synthesize_scene_raises_on_non_200(tmp_path):
    out_path = str(tmp_path / "scene_01.mp3")
    fake_resp = MagicMock(status_code=401, text="unauthorized")

    with patch("agent_video.tts.requests.post", return_value=fake_resp):
        with pytest.raises(TTSError, match="401"):
            synthesize_scene("hello", out_path, api_key="bad", voice_id="voiceABC")


def test_get_audio_duration_parses_ffprobe_json():
    fake_ffprobe_result = MagicMock(stdout=json.dumps({"format": {"duration": "4.25"}}))

    with patch("agent_video.tts.get_ffmpeg_exe", return_value="C:/fake/ffmpeg.exe"):
        with patch("agent_video.tts.os.path.isfile", return_value=True):
            with patch("agent_video.tts.subprocess.run", return_value=fake_ffprobe_result):
                duration = get_audio_duration("scene_01.mp3")

    assert duration == 4.25
