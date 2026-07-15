"""Tests for the S3-backed TTS cache store and provider cache-key fields."""
import os

from moto import mock_aws

from saas.tts_providers import AZURE_OUTPUT_FORMAT, AzureTTS, ElevenLabsTTS


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


@mock_aws
def test_object_store_roundtrip(tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket
    from saas.tts_cache_store import ObjectStorageCacheStore

    ensure_bucket()
    store = ObjectStorageCacheStore()

    src = tmp_path / "src.mp3"
    src.write_bytes(b"audio-bytes")
    store.store("abc123", str(src))

    dest = tmp_path / "dest.mp3"
    assert store.fetch("abc123", str(dest)) is True
    assert dest.read_bytes() == b"audio-bytes"

    from saas.object_storage import get_s3_client

    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key="tts_cache/abc123.mp3")["Body"].read()
    assert body == b"audio-bytes"


@mock_aws
def test_object_store_fetch_miss_returns_false(tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket
    from saas.tts_cache_store import ObjectStorageCacheStore

    ensure_bucket()
    store = ObjectStorageCacheStore()
    assert store.fetch("nope", str(tmp_path / "dest.mp3")) is False


def test_elevenlabs_cache_key_fields():
    fields = ElevenLabsTTS().cache_key_fields("Hello", voice="v1", language="en", style=0.6)
    assert fields == {
        "provider": "elevenlabs",
        "model_id": "eleven_multilingual_v2",
        "voice": "v1",
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.6,
        "text": "Hello",
    }


def test_elevenlabs_cache_key_fields_resolves_env_voice(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "env-voice")
    fields = ElevenLabsTTS().cache_key_fields("Hello", voice="", language="en")
    assert fields["voice"] == "env-voice"


def test_azure_cache_key_fields_exclude_style():
    fields = AzureTTS().cache_key_fields("Hello", voice="en-US-GuyNeural", language="en", style=0.9)
    assert fields == {
        "provider": "azure",
        "voice": "en-US-GuyNeural",
        "language": "en",
        "output_format": AZURE_OUTPUT_FORMAT,
        "text": "Hello",
    }
    assert "style" not in fields
