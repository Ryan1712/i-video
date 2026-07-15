import pytest

import saas.tts_providers as tp
from saas.tts_providers import AzureTTS, ElevenLabsTTS, get_tts_provider


def test_factory_defaults_to_elevenlabs(monkeypatch):
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    assert isinstance(get_tts_provider(), ElevenLabsTTS)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "azure")
    assert isinstance(get_tts_provider(), AzureTTS)


def test_factory_explicit_name_wins(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    assert isinstance(get_tts_provider("azure"), AzureTTS)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_tts_provider("bogus")


def test_elevenlabs_delegates_to_engine(monkeypatch):
    calls = {}

    def fake_synthesize_scene(text, out_path, api_key, voice_id, style=0.0):
        calls.update(text=text, out_path=out_path, api_key=api_key, voice_id=voice_id)

    monkeypatch.setattr(tp, "synthesize_scene", fake_synthesize_scene)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env-voice")

    ElevenLabsTTS().synthesize("hello", "/tmp/a.mp3", voice="v-42", language="en")
    assert calls == {"text": "hello", "out_path": "/tmp/a.mp3", "api_key": "el-key", "voice_id": "v-42"}

    ElevenLabsTTS().synthesize("hello", "/tmp/a.mp3", voice="", language="en")
    assert calls["voice_id"] == "env-voice"  # falls back to env


def test_azure_builds_ssml_and_writes_file(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        text = ""

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(tp.requests, "post", fake_post)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "southeastasia")

    out = tmp_path / "a.mp3"
    AzureTTS().synthesize("xin chào", str(out), voice="vi-VN-HoaiMyNeural", language="vi")
    assert out.read_bytes() == b"mp3-bytes"
    assert "southeastasia" in captured["url"]
    assert "vi-VN-HoaiMyNeural" in captured["data"].decode()
    assert "xin ch" in captured["data"].decode()


def test_azure_escapes_voice_in_ssml(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        text = ""

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["data"] = data
        return FakeResponse()

    monkeypatch.setattr(tp.requests, "post", fake_post)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "southeastasia")

    out = tmp_path / "a.mp3"
    malicious_voice = "vi-VN' /><evil x='"
    AzureTTS().synthesize("hello", str(out), voice=malicious_voice, language="vi")

    ssml = captured["data"].decode()
    assert "&apos;" in ssml
    assert "' /><evil x='" not in ssml


def test_elevenlabs_passes_style_through(monkeypatch):
    calls = {}

    def fake_synthesize_scene(text, out_path, api_key, voice_id, style=0.0):
        calls.update(style=style)

    monkeypatch.setattr(tp, "synthesize_scene", fake_synthesize_scene)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    ElevenLabsTTS().synthesize("hello", "/tmp/a.mp3", voice="v-42", language="en", style=0.7)
    assert calls["style"] == 0.7


def test_azure_accepts_and_ignores_style(monkeypatch, tmp_path):
    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        text = ""

    monkeypatch.setattr(tp.requests, "post", lambda *a, **k: FakeResponse())
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "southeastasia")

    out = tmp_path / "a.mp3"
    AzureTTS().synthesize("hello", str(out), voice="en-US-GuyNeural", language="en", style=0.7)
    assert out.read_bytes() == b"mp3-bytes"
