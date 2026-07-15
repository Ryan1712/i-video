from unittest.mock import MagicMock, patch

import pytest
import requests

from agent_video.music import MusicError, generate_music


def test_generate_music_raises_without_api_key():
    with pytest.raises(MusicError, match="ELEVENLABS_API_KEY"):
        generate_music("tense ambient", 60_000, api_key="")


def test_generate_music_rejects_out_of_range_duration():
    with pytest.raises(MusicError, match="duration_ms"):
        generate_music("tense ambient", 700_000, api_key="key123")


def test_generate_music_returns_audio_bytes_on_success():
    fake_resp = MagicMock(status_code=200, content=b"fake-mp3-bytes")

    with patch("agent_video.music.requests.post", return_value=fake_resp) as post_mock:
        result = generate_music("tense ambient", 60_000, api_key="key123")

    assert result == b"fake-mp3-bytes"
    assert post_mock.call_args[0][0] == "https://api.elevenlabs.io/v1/music"
    assert post_mock.call_args[1]["headers"]["xi-api-key"] == "key123"
    assert post_mock.call_args[1]["json"] == {
        "prompt": "tense ambient",
        "music_length_ms": 60_000,
        "force_instrumental": True,
    }


def test_generate_music_raises_on_non_200():
    fake_resp = MagicMock(status_code=422, text="invalid prompt")

    with patch("agent_video.music.requests.post", return_value=fake_resp):
        with pytest.raises(MusicError, match="422"):
            generate_music("tense ambient", 60_000, api_key="key123")


def test_generate_music_raises_on_connection_error():
    with patch(
        "agent_video.music.requests.post",
        side_effect=requests.exceptions.ConnectionError("reset"),
    ):
        with pytest.raises(MusicError, match="request failed"):
            generate_music("tense ambient", 60_000, api_key="key123")
