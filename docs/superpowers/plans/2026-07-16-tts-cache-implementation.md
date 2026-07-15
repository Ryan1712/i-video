# TTS Content-Hash Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuilding an episode only calls the TTS provider for scenes whose input changed, in both the CLI and the SaaS build task.

**Architecture:** One engine module (`agent_video/tts_cache.py`) owns the hash computation and the get-or-synthesize flow, with a pluggable store protocol (`fetch(key, dest_path) -> bool`, `store(key, src_path) -> None`). The CLI uses a local-directory store; the SaaS build task uses a MinIO/S3 store defined in `saas/` (engine never imports SaaS). Cache failures degrade to a miss — they never fail a build.

**Tech Stack:** Python 3.12, pytest, unittest.mock, moto (`@mock_aws`) for S3 tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-tts-cache-design.md`

## Global Constraints

- Run all tests from repo root `d:\Video\agent_video` with `python -m pytest tests/ -q`.
- Cache key = SHA-256 hex of canonical JSON (`sort_keys=True`) of the declared fields plus `"cache_version": TTS_CACHE_VERSION` (starts at 1).
- Azure key fields deliberately exclude `style` (AzureTTS ignores it).
- Env `TTS_CACHE=off` (also `0`, `false`) bypasses the cache entirely at call sites.
- Exceptions from `fetch`/`store` are logged as warnings and treated as miss/no-op; synthesis errors propagate unchanged.
- All commits on branch `phase1-series-agent`, end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Engine cache module — key computation and enable flag

**Files:**
- Create: `agent_video/tts_cache.py`
- Test: `tests/test_tts_cache.py`

**Interfaces:**
- Produces: `TTS_CACHE_VERSION: int` (module constant, value 1); `compute_cache_key(fields: dict) -> str` (sha256 hexdigest); `tts_cache_enabled() -> bool` (reads env `TTS_CACHE`, default on). Later tasks import all three from `agent_video.tts_cache`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tts_cache.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tts_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_video.tts_cache'`

- [ ] **Step 3: Write minimal implementation**

Create `agent_video/tts_cache.py`:

```python
"""Content-hash cache for TTS audio: reuse synthesized speech when the input is unchanged."""
from __future__ import annotations

import hashlib
import json
import os

# Bump whenever TTS behavior changes in a way that makes previously cached audio stale
# (e.g. different post-processing). Old cache entries then simply stop matching.
TTS_CACHE_VERSION = 1


def compute_cache_key(fields: dict) -> str:
    payload = dict(fields)
    payload["cache_version"] = TTS_CACHE_VERSION
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tts_cache_enabled() -> bool:
    return os.environ.get("TTS_CACHE", "on").strip().lower() not in ("off", "0", "false")
```

Note: `test_version_bump_changes_key` patches the module attribute, so `compute_cache_key` must read `TTS_CACHE_VERSION` at call time. In a plain module function, `payload["cache_version"] = TTS_CACHE_VERSION` resolves the global at call time — do NOT capture it as a default argument or module-load-time constant inside the function.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tts_cache.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add agent_video/tts_cache.py tests/test_tts_cache.py
git commit -m "feat: add TTS cache key computation and enable flag

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: LocalCacheStore and synthesize_with_cache

**Files:**
- Modify: `agent_video/tts_cache.py`
- Test: `tests/test_tts_cache.py` (append)

**Interfaces:**
- Consumes: `compute_cache_key` from Task 1.
- Produces: `LocalCacheStore(root_dir: str)` with `fetch(key: str, dest_path: str) -> bool` and `store(key: str, src_path: str) -> None`; `synthesize_with_cache(key_fields: dict, synth_fn: Callable[[str], None], out_path: str, store, force: bool = False) -> bool` (returns True on cache hit). Tasks 3 and 5 import both from `agent_video.tts_cache`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tts_cache.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tts_cache.py -q`
Expected: FAIL — `ImportError: cannot import name 'LocalCacheStore'`

- [ ] **Step 3: Write minimal implementation**

Add to `agent_video/tts_cache.py` (below the existing code; add `import logging`, `import shutil` and `from typing import Callable` to the imports at the top):

```python
logger = logging.getLogger(__name__)


class LocalCacheStore:
    """Cache entries as <root_dir>/<key>.mp3 on the local filesystem."""

    def __init__(self, root_dir: str) -> None:
        self.root_dir = root_dir

    def _entry_path(self, key: str) -> str:
        return os.path.join(self.root_dir, f"{key}.mp3")

    def fetch(self, key: str, dest_path: str) -> bool:
        entry = self._entry_path(key)
        if not os.path.isfile(entry):
            return False
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        shutil.copyfile(entry, dest_path)
        return True

    def store(self, key: str, src_path: str) -> None:
        os.makedirs(self.root_dir, exist_ok=True)
        shutil.copyfile(src_path, self._entry_path(key))


def synthesize_with_cache(
    key_fields: dict,
    synth_fn: Callable[[str], None],
    out_path: str,
    store,
    force: bool = False,
) -> bool:
    """Fetch cached audio into out_path, or synthesize and store it. Returns True on hit.

    Storage failures are logged and degrade to a miss/no-op; synthesis errors propagate.
    """
    key = compute_cache_key(key_fields)
    if not force:
        try:
            if store.fetch(key, out_path):
                return True
        except Exception as exc:
            logger.warning("TTS cache fetch failed (%s); synthesizing instead", exc)
    synth_fn(out_path)
    try:
        store.store(key, out_path)
    except Exception as exc:
        logger.warning("TTS cache store failed (%s); continuing without caching", exc)
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tts_cache.py -q`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add agent_video/tts_cache.py tests/test_tts_cache.py
git commit -m "feat: add LocalCacheStore and synthesize_with_cache

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: ElevenLabs constants and CLI wiring

**Files:**
- Modify: `agent_video/tts.py` (extract constants used in the request payload)
- Modify: `agent_video/cli.py` (`cmd_build` TTS loop, around lines 74-86)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `LocalCacheStore`, `synthesize_with_cache`, `tts_cache_enabled` from `agent_video.tts_cache`.
- Produces: `ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"`, `ELEVENLABS_STABILITY = 0.5`, `ELEVENLABS_SIMILARITY = 0.75` as module constants in `agent_video/tts.py` (Task 4's provider also imports these).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def _fake_synth(text, out_path, api_key, voice_id, style=0.0):
    with open(out_path, "wb") as f:
        f.write(b"audio:" + text.encode("utf-8"))


def _build_ready_episode_dir(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    open(os.path.join(ep_dir, "assets", "hero.png"), "wb").close()
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)
    return ep_dir, common_dir


def test_cmd_build_second_run_uses_tts_cache(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)

    common_patches = dict(
        get_audio_duration=3.0,
        output=os.path.join(ep_dir, "output", "episode.mp4"),
    )
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}

    with patch.dict(os.environ, env):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth1, \
             patch("agent_video.cli.get_audio_duration", return_value=common_patches["get_audio_duration"]), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=common_patches["output"]):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth1.call_count == 1

        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth2, \
             patch("agent_video.cli.get_audio_duration", return_value=common_patches["get_audio_duration"]), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=common_patches["output"]):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth2.call_count == 0

    # cache lives next to the episode dir
    cache_dir = os.path.join(str(tmp_path), ".tts_cache")
    assert os.path.isdir(cache_dir)
    assert len(os.listdir(cache_dir)) == 1


def test_cmd_build_tts_cache_off_env_disables_cache(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v", "TTS_CACHE": "off"}

    with patch.dict(os.environ, env):
        for _ in range(2):
            with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth, \
                 patch("agent_video.cli.get_audio_duration", return_value=3.0), \
                 patch("agent_video.cli.build_scene_clip"), \
                 patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
                cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
            assert synth.call_count == 1

    assert not os.path.isdir(os.path.join(str(tmp_path), ".tts_cache"))


def test_cmd_build_changed_text_synthesizes_again(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}

    with patch.dict(os.environ, env):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth1, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth1.call_count == 1

        with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
            f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hello again\n")

        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth2, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth2.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -q`
Expected: the three new tests FAIL (second run still calls synthesize — `synth2.call_count == 0` assertion fails); pre-existing tests still pass.

- [ ] **Step 3: Extract constants in `agent_video/tts.py`**

Add after `ELEVENLABS_TTS_URL`:

```python
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
ELEVENLABS_STABILITY = 0.5
ELEVENLABS_SIMILARITY = 0.75
```

And in `synthesize_scene`, replace the request `json=` payload with:

```python
                json={
                    "text": text,
                    "model_id": ELEVENLABS_MODEL_ID,
                    "voice_settings": {
                        "stability": ELEVENLABS_STABILITY,
                        "similarity_boost": ELEVENLABS_SIMILARITY,
                        "style": style,
                    },
                },
```

- [ ] **Step 4: Wire the cache into `cmd_build` in `agent_video/cli.py`**

Add imports at the top:

```python
from .tts import ELEVENLABS_MODEL_ID, ELEVENLABS_SIMILARITY, ELEVENLABS_STABILITY
from .tts_cache import LocalCacheStore, synthesize_with_cache, tts_cache_enabled
```

Replace the TTS loop (currently):

```python
    audio_paths = []
    durations = []
    for scene in episode.scenes:
        audio_path = os.path.join(video_dir, "audio", f"{scene.name}.mp3")
        synthesize_scene(scene.text, audio_path, api_key, voice_id)
        duration = get_audio_duration(audio_path)
        audio_paths.append(audio_path)
        durations.append(duration)
    print(f"Bước 2/4: Tạo giọng đọc...                 ✓ {len(episode.scenes)} scene")
```

with:

```python
    audio_paths = []
    durations = []
    cache_store = LocalCacheStore(os.path.join(os.path.dirname(os.path.abspath(video_dir)), ".tts_cache"))
    cache_hits = 0
    for scene in episode.scenes:
        audio_path = os.path.join(video_dir, "audio", f"{scene.name}.mp3")
        if tts_cache_enabled():
            key_fields = {
                "provider": "elevenlabs",
                "model_id": ELEVENLABS_MODEL_ID,
                "voice": voice_id,
                "stability": ELEVENLABS_STABILITY,
                "similarity_boost": ELEVENLABS_SIMILARITY,
                "style": 0.0,
                "text": scene.text,
            }
            hit = synthesize_with_cache(
                key_fields,
                lambda p, t=scene.text: synthesize_scene(t, p, api_key, voice_id),
                audio_path,
                cache_store,
            )
            cache_hits += 1 if hit else 0
        else:
            synthesize_scene(scene.text, audio_path, api_key, voice_id)
        duration = get_audio_duration(audio_path)
        audio_paths.append(audio_path)
        durations.append(duration)
    cache_note = f" ({cache_hits} từ cache)" if cache_hits else ""
    print(f"Bước 2/4: Tạo giọng đọc...                 ✓ {len(episode.scenes)} scene{cache_note}")
```

Note the `t=scene.text` default argument in the lambda: it binds the loop variable at definition time (defensive; the lambda is invoked immediately, but this keeps it correct if the flow ever changes).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py tests/test_tts_cache.py -q`
Expected: all pass (including the pre-existing CLI tests)

- [ ] **Step 6: Commit**

```bash
git add agent_video/tts.py agent_video/cli.py tests/test_cli.py
git commit -m "feat: use TTS content-hash cache in CLI build

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: SaaS object-storage store and provider cache-key fields

**Files:**
- Create: `saas/tts_cache_store.py`
- Modify: `saas/tts_providers.py` (add `AZURE_OUTPUT_FORMAT` constant and `cache_key_fields` methods)
- Test: `tests/saas/test_tts_cache_store.py`

**Interfaces:**
- Consumes: `ELEVENLABS_MODEL_ID`, `ELEVENLABS_STABILITY`, `ELEVENLABS_SIMILARITY` from `agent_video.tts` (Task 3); `get_s3_client`, `_bucket_name`, `upload_bytes` from `saas.object_storage`.
- Produces: `ObjectStorageCacheStore` (no-arg constructor) with `fetch(key, dest_path) -> bool` / `store(key, src_path) -> None`, objects at `tts_cache/<key>.mp3`; `ElevenLabsTTS.cache_key_fields(text, voice, language, style=0.0) -> dict` and `AzureTTS.cache_key_fields(text, voice, language, style=0.0) -> dict`. Task 5 uses both.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_tts_cache_store.py`:

```python
"""Tests for the S3-backed TTS cache store and provider cache-key fields."""
import os
from unittest.mock import patch

import pytest
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/saas/test_tts_cache_store.py -q`
Expected: FAIL — `ImportError: cannot import name 'AZURE_OUTPUT_FORMAT'`

- [ ] **Step 3: Implement store and key fields**

Create `saas/tts_cache_store.py`:

```python
"""S3/MinIO-backed TTS cache store: objects at tts_cache/<key>.mp3, shared across all users."""
from __future__ import annotations

from botocore.exceptions import ClientError

from .object_storage import _bucket_name, get_s3_client, upload_bytes

CACHE_PREFIX = "tts_cache/"


class ObjectStorageCacheStore:
    def _object_key(self, key: str) -> str:
        return f"{CACHE_PREFIX}{key}.mp3"

    def fetch(self, key: str, dest_path: str) -> bool:
        client = get_s3_client()
        try:
            client.download_file(_bucket_name(), self._object_key(key), dest_path)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey"):
                return False
            raise

    def store(self, key: str, src_path: str) -> None:
        with open(src_path, "rb") as f:
            upload_bytes(self._object_key(key), f.read())
```

In `saas/tts_providers.py`, add after `AZURE_TTS_URL`:

```python
AZURE_OUTPUT_FORMAT = "audio-24khz-96kbitrate-mono-mp3"
```

Replace the hardcoded `"X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3"` header value in `AzureTTS.synthesize` with `AZURE_OUTPUT_FORMAT`.

Extend the import from the engine:

```python
from agent_video.tts import (
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_SIMILARITY,
    ELEVENLABS_STABILITY,
    TTSError,
    synthesize_scene,
)
```

Add `cache_key_fields` to `ElevenLabsTTS` (voice resolution MUST mirror `synthesize`'s `voice or os.environ.get("ELEVENLABS_VOICE_ID", "")` fallback, otherwise an empty `voice` would collide across different env voices):

```python
    def cache_key_fields(self, text: str, voice: str, language: str, style: float = 0.0) -> dict:
        return {
            "provider": "elevenlabs",
            "model_id": ELEVENLABS_MODEL_ID,
            "voice": voice or os.environ.get("ELEVENLABS_VOICE_ID", ""),
            "stability": ELEVENLABS_STABILITY,
            "similarity_boost": ELEVENLABS_SIMILARITY,
            "style": style,
            "text": text,
        }
```

Add `cache_key_fields` to `AzureTTS` (`style` accepted for interface uniformity but deliberately excluded — Azure ignores it, see spec):

```python
    def cache_key_fields(self, text: str, voice: str, language: str, style: float = 0.0) -> dict:
        return {
            "provider": "azure",
            "voice": voice,
            "language": language,
            "output_format": AZURE_OUTPUT_FORMAT,
            "text": text,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/saas/test_tts_cache_store.py tests/saas/test_tts_providers.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add saas/tts_cache_store.py saas/tts_providers.py tests/saas/test_tts_cache_store.py
git commit -m "feat: add S3 TTS cache store and provider cache-key fields

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire cache into the SaaS build task

**Files:**
- Modify: `saas/tasks.py` (TTS loop in `run_build`, around lines 63-82)
- Test: `tests/saas/test_build_cache.py`

**Interfaces:**
- Consumes: `synthesize_with_cache`, `tts_cache_enabled` from `agent_video.tts_cache`; `ObjectStorageCacheStore` from `saas.tts_cache_store`; `cache_key_fields` from the provider instances (Task 4).
- Produces: job stage strings gain a running hit count when hits occur: `tts {i}/{total} ({hits} cached)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_build_cache.py`:

```python
"""Integration: SaaS build task reuses cached TTS audio across builds."""
from unittest.mock import patch

from moto import mock_aws

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def _fake_synth(text, out_path, api_key, voice_id, style=0.0):
    with open(out_path, "wb") as f:
        f.write(b"audio:" + text.encode("utf-8"))


def _make_episode(db_session, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="cache@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Cache Test", description="", tags="", status="ready")
    scene = Scene(order_index=0, narration_text="Hello world", asset_object_key=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    key = f"episodes/{episode.id}/scenes/{scene.id}.png"
    upload_bytes(key, b"fake-png-bytes")
    scene.asset_object_key = key
    db_session.commit()
    return episode, scene


def _new_build_job(db_session, episode_id):
    job = Job(episode_id=episode_id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()
    return job.id


def _run(job_id, db_session_factory, tmp_path):
    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")
    with patch("saas.tts_providers.synthesize_scene", side_effect=_fake_synth) as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)):
        run_build(job_id, db_session_factory)
    return synth_mock


@mock_aws
def test_second_build_makes_zero_tts_calls(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, _ = _make_episode(db_session, monkeypatch)

    synth1 = _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path)
    assert synth1.call_count == 1

    # reset episode so it can build again
    episode.status = "ready"
    db_session.commit()

    synth2 = _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path)
    assert synth2.call_count == 0

    fresh = db_session_factory()
    assert fresh.query(Job).filter_by(episode_id=episode.id).order_by(Job.id.desc()).first().status == "done"
    fresh.close()


@mock_aws
def test_changed_narration_synthesizes_only_changed_scene(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, scene = _make_episode(db_session, monkeypatch)

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1

    scene.narration_text = "Hello again"
    episode.status = "ready"
    db_session.commit()

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1


@mock_aws
def test_tts_cache_off_disables_cache(db_session, db_session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_CACHE", "off")
    episode, _ = _make_episode(db_session, monkeypatch)

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1
    episode.status = "ready"
    db_session.commit()
    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/saas/test_build_cache.py -q`
Expected: `test_second_build_makes_zero_tts_calls` and `test_changed_narration_synthesizes_only_changed_scene` FAIL (`synth2.call_count == 0` is violated); the `TTS_CACHE=off` test may already pass.

- [ ] **Step 3: Wire the cache into `run_build` in `saas/tasks.py`**

Add imports:

```python
from agent_video.tts_cache import synthesize_with_cache, tts_cache_enabled

from .tts_cache_store import ObjectStorageCacheStore
```

Replace the TTS loop (currently):

```python
            for index, scene in enumerate(engine_episode.scenes):
                job.stage = f"tts {index + 1}/{total}"
                job.progress_pct = int((index + 1) / total * 50)
                db.commit()
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                tts.synthesize(scene.text, audio_path, voice=voice, language=language, style=voice_style)
                duration = get_audio_duration(audio_path)
                audio_paths.append(audio_path)
                durations.append(duration)
```

with:

```python
            cache_store = ObjectStorageCacheStore()
            cache_hits = 0
            for index, scene in enumerate(engine_episode.scenes):
                cache_note = f" ({cache_hits} cached)" if cache_hits else ""
                job.stage = f"tts {index + 1}/{total}{cache_note}"
                job.progress_pct = int((index + 1) / total * 50)
                db.commit()
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                if tts_cache_enabled():
                    hit = synthesize_with_cache(
                        tts.cache_key_fields(scene.text, voice=voice, language=language, style=voice_style),
                        lambda p, t=scene.text: tts.synthesize(t, p, voice=voice, language=language, style=voice_style),
                        audio_path,
                        cache_store,
                    )
                    cache_hits += 1 if hit else 0
                else:
                    tts.synthesize(scene.text, audio_path, voice=voice, language=language, style=voice_style)
                duration = get_audio_duration(audio_path)
                audio_paths.append(audio_path)
                durations.append(duration)
```

- [ ] **Step 4: Run the new tests and the whole backend suite**

Run: `python -m pytest tests/saas/test_build_cache.py -q`
Expected: 3 passed

Run: `python -m pytest tests/ -q`
Expected: all pass. Watch `tests/saas/test_tasks.py` and `tests/saas/test_build_progress.py` in particular: existing tests mock `synthesize_scene` without writing the output file, so the cache's `store()` will log a warning and continue — they must still pass unchanged. Stage strings only gain the `(N cached)` suffix when hits occur, which never happens in those tests.

- [ ] **Step 5: Commit**

```bash
git add saas/tasks.py tests/saas/test_build_cache.py
git commit -m "feat: use TTS content-hash cache in SaaS build task

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
