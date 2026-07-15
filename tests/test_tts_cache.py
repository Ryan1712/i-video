"""Tests for the TTS content-hash cache."""
import os
from unittest.mock import patch

from agent_video.tts_cache import compute_cache_key, tts_cache_enabled

BASE_FIELDS = {
    "provider": "elevenlabs",
    "model_id": "eleven_multilingual_v2",
    "voice": "v1",
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "text": "Hello world",
}


def test_same_fields_produce_same_key():
    assert compute_cache_key(dict(BASE_FIELDS)) == compute_cache_key(dict(BASE_FIELDS))


def test_key_is_sha256_hex():
    key = compute_cache_key(dict(BASE_FIELDS))
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_each_field_change_changes_key():
    base_key = compute_cache_key(dict(BASE_FIELDS))
    for field, new_value in [
        ("provider", "azure"),
        ("model_id", "other_model"),
        ("voice", "v2"),
        ("stability", 0.4),
        ("similarity_boost", 0.5),
        ("style", 0.9),
        ("text", "Hello world!"),
    ]:
        changed = dict(BASE_FIELDS)
        changed[field] = new_value
        assert compute_cache_key(changed) != base_key, field


def test_field_order_does_not_matter():
    reordered = dict(reversed(list(BASE_FIELDS.items())))
    assert compute_cache_key(reordered) == compute_cache_key(dict(BASE_FIELDS))


def test_version_bump_changes_key():
    key_v1 = compute_cache_key(dict(BASE_FIELDS))
    with patch("agent_video.tts_cache.TTS_CACHE_VERSION", 2):
        assert compute_cache_key(dict(BASE_FIELDS)) != key_v1


def test_cache_enabled_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TTS_CACHE", None)
        assert tts_cache_enabled() is True


def test_cache_disabled_by_env_values():
    for value in ("off", "OFF", "0", "false", "False"):
        with patch.dict(os.environ, {"TTS_CACHE": value}):
            assert tts_cache_enabled() is False, value


def test_cache_enabled_for_other_values():
    for value in ("on", "1", "true", "yes"):
        with patch.dict(os.environ, {"TTS_CACHE": value}):
            assert tts_cache_enabled() is True, value
