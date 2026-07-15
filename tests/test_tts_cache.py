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


from agent_video.tts_cache import LocalCacheStore, synthesize_with_cache


def _fields(text="Hello world"):
    fields = dict(BASE_FIELDS)
    fields["text"] = text
    return fields


def _writing_synth(content=b"fresh-audio"):
    calls = []

    def synth(out_path):
        calls.append(out_path)
        with open(out_path, "wb") as f:
            f.write(content)

    synth.calls = calls
    return synth


def test_local_store_roundtrip(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))
    src = tmp_path / "src.mp3"
    src.write_bytes(b"audio-bytes")

    store.store("abc123", str(src))

    dest = tmp_path / "out" / "dest.mp3"
    assert store.fetch("abc123", str(dest)) is True
    assert dest.read_bytes() == b"audio-bytes"


def test_local_store_fetch_miss_returns_false(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))
    dest = tmp_path / "dest.mp3"
    assert store.fetch("missing", str(dest)) is False
    assert not dest.exists()


def test_miss_calls_synth_and_stores(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))
    synth = _writing_synth()
    out = tmp_path / "audio" / "scene.mp3"

    hit = synthesize_with_cache(_fields(), synth, str(out), store)

    assert hit is False
    assert len(synth.calls) == 1
    assert out.read_bytes() == b"fresh-audio"
    # Stored: a second call with same fields must not synthesize again.
    synth2 = _writing_synth(b"should-not-be-written")
    out2 = tmp_path / "audio" / "scene2.mp3"
    hit2 = synthesize_with_cache(_fields(), synth2, str(out2), store)
    assert hit2 is True
    assert len(synth2.calls) == 0
    assert out2.read_bytes() == b"fresh-audio"


def test_different_text_misses(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))
    out1 = tmp_path / "a.mp3"
    out2 = tmp_path / "b.mp3"
    synthesize_with_cache(_fields("one"), _writing_synth(b"one"), str(out1), store)
    synth = _writing_synth(b"two")
    hit = synthesize_with_cache(_fields("two"), synth, str(out2), store)
    assert hit is False
    assert len(synth.calls) == 1
    assert out2.read_bytes() == b"two"


def test_force_skips_fetch_but_still_stores(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))
    out1 = tmp_path / "a.mp3"
    synthesize_with_cache(_fields(), _writing_synth(b"old"), str(out1), store)

    synth = _writing_synth(b"new")
    out2 = tmp_path / "b.mp3"
    hit = synthesize_with_cache(_fields(), synth, str(out2), store, force=True)
    assert hit is False
    assert len(synth.calls) == 1
    assert out2.read_bytes() == b"new"
    # force refreshed the stored entry
    out3 = tmp_path / "c.mp3"
    assert synthesize_with_cache(_fields(), _writing_synth(b"x"), str(out3), store) is True
    assert out3.read_bytes() == b"new"


class _BrokenStore:
    def fetch(self, key, dest_path):
        raise RuntimeError("storage down")

    def store(self, key, src_path):
        raise RuntimeError("storage down")


def test_broken_store_still_produces_audio(tmp_path):
    synth = _writing_synth(b"audio")
    out = tmp_path / "scene.mp3"

    hit = synthesize_with_cache(_fields(), synth, str(out), _BrokenStore())

    assert hit is False
    assert len(synth.calls) == 1
    assert out.read_bytes() == b"audio"


def test_synthesis_error_propagates(tmp_path):
    store = LocalCacheStore(str(tmp_path / "cache"))

    def failing_synth(out_path):
        raise RuntimeError("provider exploded")

    import pytest

    with pytest.raises(RuntimeError, match="provider exploded"):
        synthesize_with_cache(_fields(), failing_synth, str(tmp_path / "x.mp3"), store)
