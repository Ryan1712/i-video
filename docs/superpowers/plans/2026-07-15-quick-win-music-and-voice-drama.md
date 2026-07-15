# Quick-Win Music & Voice Drama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 1 of `docs/superpowers/specs/2026-07-15-content-quality-roadmap-design.md` — add a whole-episode background music track and more dramatic ElevenLabs voice delivery to EP1, using only hooks that already exist in the build pipeline.

**Architecture:** Two independent additive changes to `saas/tasks.py::run_build`: (1) an optional `style` float threaded from `Series.style["voice_style"]` through the existing TTS provider interface into `agent_video/tts.py`'s ElevenLabs call; (2) a new `agent_video/music.py` client for ElevenLabs' Music API, whose output is stored once via a new `saas/storage.py` helper and referenced by `Series.style["music_object_key"]`, downloaded into the build's `temp_dir/music.mp3` where `agent_video/video_builder.py` already knows how to mix it in. No new DB tables or migrations — both new fields live in the existing `Series.style` JSON dict, the same pattern already used for `voice_id`/`tts_provider`.

**Tech Stack:** Python, SQLAlchemy, `requests`, ElevenLabs Text-to-Speech API (existing) and Music API (`POST https://api.elevenlabs.io/v1/music`, new), pytest + `moto` for S3 mocking (existing).

## Global Constraints

- New per-series settings (`voice_style`, `music_object_key`) live in the existing `Series.style` JSON column — do not add a migration or new table.
- Both TTS provider classes (`ElevenLabsTTS`, `AzureTTS` in `saas/tts_providers.py`) must keep an identical `synthesize(text, out_path, voice, language, style=0.0)` signature — Azure accepts `style` and ignores it, so `saas/tasks.py` can call either uniformly.
- All new external API calls fail fast on non-2xx responses (raise immediately, no retry-masking of real errors) — matches the existing `TTSError`/`ImageError` convention. A bounded connection-error retry (see `agent_video/tts.py::synthesize_scene`) is NOT required here: these are one-off manual-script calls, not the 37-call sequential build loop that motivated that retry.
- Any full EP1 (episode 6) rebuild must be preceded by a short 1-2 scene test build first (build only the first 2-3 scenes, verify audio/visuals look right) before spending time/API cost on the full ~9-minute rebuild. This is a standing user preference, not new for this plan.
- All one-off scripts and DB scripts on this machine must be run with the `py` launcher (`py script.py` / `py -c "..."`) from `D:\Video\agent_video`, not `python` — `python` does not resolve the `agent_video` package here. `load_dotenv()` must be called with the file's own path resolution in mind: `load_dotenv()` alone only works when invoked via `-c` (cwd-based search); scripts under `scripts/` already handle this correctly (see existing `scripts/compare_tts_en.py`), but any script run from outside `D:\Video\agent_video` must call `load_dotenv(r"D:\Video\agent_video\.env")` explicitly or exhibit the port-5432-fallback bug seen during the previous plan's execution.

---

### Task 1: Add a `style` parameter to the ElevenLabs TTS engine call

**Files:**
- Modify: `agent_video/tts.py:22-44` (`synthesize_scene`)
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `synthesize_scene(text, out_path, api_key, voice_id, style: float = 0.0)` — Task 2 calls this with a real `style` value via the provider layer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tts.py`:

```python
def test_synthesize_scene_includes_style_in_voice_settings(tmp_path):
    out_path = str(tmp_path / "scene_01.mp3")
    fake_resp = MagicMock(status_code=200, content=b"fake-mp3-bytes")

    with patch("agent_video.tts.requests.post", return_value=fake_resp) as post_mock:
        synthesize_scene("hello", out_path, api_key="key123", voice_id="voiceABC", style=0.6)

    assert post_mock.call_args[1]["json"]["voice_settings"]["style"] == 0.6


def test_synthesize_scene_style_defaults_to_zero(tmp_path):
    out_path = str(tmp_path / "scene_01.mp3")
    fake_resp = MagicMock(status_code=200, content=b"fake-mp3-bytes")

    with patch("agent_video.tts.requests.post", return_value=fake_resp) as post_mock:
        synthesize_scene("hello", out_path, api_key="key123", voice_id="voiceABC")

    assert post_mock.call_args[1]["json"]["voice_settings"]["style"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_tts.py -k style -v`
Expected: both new tests FAIL with `KeyError: 'style'` (voice_settings has no `style` key yet).

- [ ] **Step 3: Add the `style` parameter and thread it into voice_settings**

In `agent_video/tts.py`, change the function signature and the `voice_settings` dict (lines 22 and 43):

```python
def synthesize_scene(text: str, out_path: str, api_key: str, voice_id: str, style: float = 0.0) -> None:
```

```python
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": style},
                },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/test_tts.py -v`
Expected: all tests in the file PASS (existing tests unaffected — they don't inspect `voice_settings["style"]`).

- [ ] **Step 5: Commit**

```bash
git add agent_video/tts.py tests/test_tts.py
git commit -m "feat(tts): add style parameter for more dramatic ElevenLabs delivery"
```

---

### Task 2: Thread `style` through the provider layer and `run_build`

**Files:**
- Modify: `saas/tts_providers.py` (`ElevenLabsTTS.synthesize`, `AzureTTS.synthesize`)
- Modify: `saas/tasks.py` (`run_build` — read `voice_style` from series style, pass through)
- Test: `tests/saas/test_tts_providers.py`, `tests/saas/test_tasks.py`

**Interfaces:**
- Consumes: `synthesize_scene(..., style: float = 0.0)` from Task 1.
- Produces: `ElevenLabsTTS.synthesize(text, out_path, voice, language, style=0.0)` and `AzureTTS.synthesize(text, out_path, voice, language, style=0.0)` — both callable uniformly from `run_build`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/saas/test_tts_providers.py`:

```python
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
```

Add to `tests/saas/test_tasks.py` (needs `Series` imported — change the existing import line to `from saas.models import Episode, Job, Scene, Series, User`):

```python
@mock_aws
def test_run_build_passes_voice_style_from_series_style(db_session, db_session_factory, tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="e2@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    series = Series(user_id=user.id, name="S", style={"voice_style": 0.6})
    db_session.add(series)
    db_session.commit()

    episode = Episode(
        user_id=user.id, series_id=series.id, title="T", description="", tags="", status="ready"
    )
    scene = Scene(order_index=0, narration_text="Hello world", asset_object_key=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    key = f"episodes/{episode.id}/scenes/{scene.id}.png"
    upload_bytes(key, b"fake-png-bytes")
    scene.asset_object_key = key
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")

    with patch("saas.tts_providers.synthesize_scene") as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)):
        run_build(job.id, db_session_factory)

    assert synth_mock.call_args[1]["style"] == 0.6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_tts_providers.py tests/saas/test_tasks.py -v`
Expected: `test_elevenlabs_passes_style_through` fails with `TypeError: synthesize() got an unexpected keyword argument 'style'`; `test_azure_accepts_and_ignores_style` fails the same way; `test_run_build_passes_voice_style_from_series_style` fails with `KeyError` (`call_args[1]` has no `style`) since `run_build` never passes it.

- [ ] **Step 3: Update both provider classes**

In `saas/tts_providers.py`:

```python
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
```

- [ ] **Step 4: Update `run_build` to read and pass `voice_style`**

In `saas/tasks.py`, in the block that currently reads:

```python
            style = episode.series.style if episode.series else {}
            tts = get_tts_provider(style.get("tts_provider"))
            voice = style.get("voice_id", "")
            language = style.get("language", "en")
```

add a `voice_style` line and use it in the synthesize call below:

```python
            style = episode.series.style if episode.series else {}
            tts = get_tts_provider(style.get("tts_provider"))
            voice = style.get("voice_id", "")
            language = style.get("language", "en")
            voice_style = style.get("voice_style", 0.0)
```

And change the synthesize call (a few lines further down) from:

```python
                tts.synthesize(scene.text, audio_path, voice=voice, language=language)
```

to:

```python
                tts.synthesize(scene.text, audio_path, voice=voice, language=language, style=voice_style)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_tts_providers.py tests/saas/test_tasks.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `py -m pytest tests/ -q`
Expected: all tests pass (same count as before plus the 3 new ones).

- [ ] **Step 7: Commit**

```bash
git add saas/tts_providers.py saas/tasks.py tests/saas/test_tts_providers.py tests/saas/test_tasks.py
git commit -m "feat(tts): thread voice_style from Series.style through to ElevenLabs calls"
```

---

### Task 3: ElevenLabs Music API client

**Files:**
- Create: `agent_video/music.py`
- Test: `tests/test_music.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `generate_music(prompt: str, duration_ms: int, api_key: str) -> bytes` and `MusicError` — Task 5's script and Task 6 call this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_music.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/test_music.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_video.music'`.

- [ ] **Step 3: Implement `agent_video/music.py`**

```python
"""ElevenLabs Music API client for generating a whole-episode background track."""
from __future__ import annotations

import requests

ELEVENLABS_MUSIC_URL = "https://api.elevenlabs.io/v1/music"

MUSIC_MIN_DURATION_MS = 3_000
MUSIC_MAX_DURATION_MS = 600_000


class MusicError(RuntimeError):
    pass


def generate_music(prompt: str, duration_ms: int, api_key: str) -> bytes:
    if not api_key:
        raise MusicError("ELEVENLABS_API_KEY not set")
    if not MUSIC_MIN_DURATION_MS <= duration_ms <= MUSIC_MAX_DURATION_MS:
        raise MusicError(
            f"duration_ms must be between {MUSIC_MIN_DURATION_MS} and "
            f"{MUSIC_MAX_DURATION_MS}, got {duration_ms}"
        )

    try:
        resp = requests.post(
            ELEVENLABS_MUSIC_URL,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"prompt": prompt, "music_length_ms": duration_ms, "force_instrumental": True},
            timeout=300,
        )
    except requests.exceptions.RequestException as exc:
        raise MusicError(f"ElevenLabs Music request failed: {exc}") from exc

    if resp.status_code != 200:
        raise MusicError(f"ElevenLabs Music failed ({resp.status_code}): {resp.text[:500]}")

    return resp.content
```

`force_instrumental=True` is hardcoded (not a parameter) because this module's only purpose is background-under-narration music, which must never compete with the narrator's voice with vocals.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/test_music.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_video/music.py tests/test_music.py
git commit -m "feat(music): add ElevenLabs Music API client for background tracks"
```

---

### Task 4: Music storage helper + wire music download into `run_build`

**Files:**
- Modify: `saas/storage.py` (add `save_series_music`)
- Modify: `saas/tasks.py` (`run_build` — download `music.mp3` into `temp_dir` when present)
- Test: `tests/saas/test_storage.py`, `tests/saas/test_tasks.py`

**Interfaces:**
- Consumes: `Series.style["music_object_key"]` (set by Task 6), `download_to_path` (existing, `saas/storage.py`).
- Produces: `save_series_music(series_id: int, filename: str, content: bytes) -> str` — Task 6 calls this to store the generated track.

- [ ] **Step 1: Write the failing tests**

Append to `tests/saas/test_storage.py`:

```python
@mock_aws
def test_save_series_music_uploads_and_returns_key(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_series_music

    ensure_bucket()
    key = save_series_music(series_id=2, filename="track.mp3", content=b"fake-mp3-bytes")

    assert key == "series/2/music.mp3"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-mp3-bytes"
```

Append to `tests/saas/test_tasks.py` (reuses the `Series` import added in Task 2):

```python
@mock_aws
def test_run_build_downloads_music_when_series_has_music_object_key(
    db_session, db_session_factory, tmp_path, monkeypatch
):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="e3@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    music_key = "series/99/music.mp3"
    upload_bytes(music_key, b"fake-music-bytes")
    series = Series(user_id=user.id, name="S", style={"music_object_key": music_key})
    db_session.add(series)
    db_session.commit()

    episode = Episode(
        user_id=user.id, series_id=series.id, title="T", description="", tags="", status="ready"
    )
    scene = Scene(order_index=0, narration_text="Hello world", asset_object_key=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    key = f"episodes/{episode.id}/scenes/{scene.id}.png"
    upload_bytes(key, b"fake-png-bytes")
    scene.asset_object_key = key
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")

    captured_video_dir = {}

    def fake_build_episode(episode, clips, audio, durations, video_dir, config):
        captured_video_dir["path"] = video_dir
        return str(fake_output_path)

    with patch("saas.tts_providers.synthesize_scene"), \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", side_effect=fake_build_episode):
        run_build(job.id, db_session_factory)

    import os

    assert os.path.isfile(os.path.join(captured_video_dir["path"], "music.mp3"))
    with open(os.path.join(captured_video_dir["path"], "music.mp3"), "rb") as f:
        assert f.read() == b"fake-music-bytes"


@mock_aws
def test_run_build_skips_music_when_series_has_no_music_object_key(
    db_session, db_session_factory, tmp_path, monkeypatch
):
    episode_id, job_id = _make_episode_with_one_scene(db_session, monkeypatch)

    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")

    captured_video_dir = {}

    def fake_build_episode(episode, clips, audio, durations, video_dir, config):
        captured_video_dir["path"] = video_dir
        return str(fake_output_path)

    with patch("saas.tts_providers.synthesize_scene"), \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", side_effect=fake_build_episode):
        run_build(job_id, db_session_factory)

    import os

    assert not os.path.isfile(os.path.join(captured_video_dir["path"], "music.mp3"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_storage.py tests/saas/test_tasks.py -v`
Expected: `test_save_series_music_uploads_and_returns_key` fails with `ImportError`; the two new `run_build` tests fail the "music.mp3 exists" assertion (first one) since nothing downloads it yet — the second one should already pass by accident (nothing to fix there, but write it now so a regression in Step 4 is caught).

- [ ] **Step 3: Add `save_series_music` to `saas/storage.py`**

Add this function (next to `save_series_asset`):

```python
def save_series_music(series_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    key = f"series/{series_id}/music{ext}"
    upload_bytes(key, content)
    return key
```

- [ ] **Step 4: Download music into `temp_dir` in `run_build` when present**

In `saas/tasks.py`, immediately after the `voice_style = style.get("voice_style", 0.0)` line added in Task 2, add:

```python
            music_key = style.get("music_object_key")
            if music_key:
                download_to_path(music_key, os.path.join(temp_dir, "music.mp3"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_storage.py tests/saas/test_tasks.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite and commit**

Run: `py -m pytest tests/ -q`
Expected: all pass.

```bash
git add saas/storage.py saas/tasks.py tests/saas/test_storage.py tests/saas/test_tasks.py
git commit -m "feat(build): download series background music into the build temp dir when set"
```

---

### Task 5: Generate comparison samples — voice style values and music prompts

**Files:**
- Create (scratch, not committed): none — this task's deliverable is the script below, which IS committed.
- Create: `scripts/compare_voice_style_and_music.py`

**Interfaces:**
- Consumes: `ElevenLabsTTS.synthesize(..., style=...)` (Task 2), `generate_music` (Task 3).
- Produces: sample files under `videos/voice_style_compare/` and `videos/music_compare/` for the user to listen to; a `voice_style` value and a chosen music prompt for Task 6 to consume. This task is done only when the user has picked both — do not proceed to Task 6 without an explicit pick, same rule as the prior plan's voice-comparison task.

- [ ] **Step 1: Write the script**

Create `scripts/compare_voice_style_and_music.py`:

```python
"""Generate ElevenLabs voice-style samples (for dramatic delivery) and short
music candidate clips (for background-music tone), for the user to pick from.

Usage (from D:\\Video\\agent_video, with .env loaded and ELEVENLABS_API_KEY set):
    py scripts/compare_voice_style_and_music.py

Voice style samples reuse the narrator voice already picked for series 2
(onwK4e9ZLuTAKqWW03F9, "Daniel") at several `style` values.
Music samples are short (30s) previews of a few candidate prompts — the full
~9-minute track is only generated in Task 6, after a prompt is picked.

Output:
    videos/voice_style_compare/style_<value>.mp3
    videos/music_compare/<name>.mp3
Listen to both sets and pick one style value and one music prompt.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent_video.music import generate_music  # noqa: E402
from saas.tts_providers import ElevenLabsTTS  # noqa: E402

SAMPLE_EN = (
    "The first scream came from the apartment upstairs. Then another, and "
    "another, until the whole building seemed to be screaming at once. "
    "Something was moving through the halls, and it was getting closer."
)

VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel, picked in the prior plan's Task 3
VOICE_STYLE_CANDIDATES = [0.0, 0.3, 0.6, 0.9]

MUSIC_PROMPT_CANDIDATES = {
    "dread_drone": (
        "tense atmospheric horror drone, sparse deep bass pulses, building dread, "
        "no melody, no vocals, suitable as quiet background under spoken narration"
    ),
    "heartbeat_tension": (
        "slow ominous heartbeat-like percussion under a thin dissonant string drone, "
        "escalating tension, no melody, no vocals, quiet background under narration"
    ),
}
MUSIC_PREVIEW_DURATION_MS = 30_000

VOICE_OUT_DIR = os.path.join("videos", "voice_style_compare")
MUSIC_OUT_DIR = os.path.join("videos", "music_compare")


def main() -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("Skipping: set ELEVENLABS_API_KEY")
        return

    os.makedirs(VOICE_OUT_DIR, exist_ok=True)
    for style in VOICE_STYLE_CANDIDATES:
        path = os.path.join(VOICE_OUT_DIR, f"style_{style}.mp3")
        print(f"voice style={style} -> {path}")
        ElevenLabsTTS().synthesize(SAMPLE_EN, path, voice=VOICE_ID, language="en", style=style)

    os.makedirs(MUSIC_OUT_DIR, exist_ok=True)
    for name, prompt in MUSIC_PROMPT_CANDIDATES.items():
        path = os.path.join(MUSIC_OUT_DIR, f"{name}.mp3")
        print(f"music '{name}' -> {path}")
        content = generate_music(prompt, MUSIC_PREVIEW_DURATION_MS, api_key)
        with open(path, "wb") as f:
            f.write(content)

    print(f"\nDone. Listen to files in {VOICE_OUT_DIR} and {MUSIC_OUT_DIR}, then pick one of each.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `py scripts/compare_voice_style_and_music.py`
Expected: 4 files in `videos/voice_style_compare/`, 2 files in `videos/music_compare/`.

- [ ] **Step 3: Open every produced file for the user and stop for their decision**

Open each file (e.g. `start "" "videos/voice_style_compare/style_0.6.mp3"` per candidate) or point the user at the directory. This task is done only when the user has told you which `style` value and which music prompt (by name, e.g. `dread_drone`) to use going forward — do not proceed to Task 6 without an explicit pick.

- [ ] **Step 4: Commit the script (not the generated audio)**

```bash
git add scripts/compare_voice_style_and_music.py
git commit -m "feat(scripts): add voice-style and music prompt comparison script"
```

---

### Task 6: Apply the chosen voice style and music to the series

**Files:**
- None (data-only, no commit — same as the prior plan's Task 4).

**Interfaces:**
- Consumes: the `style` value and music prompt name chosen in Task 5; `generate_music` (Task 3); `save_series_music` (Task 4).
- Produces: `Series.style["voice_style"]` and `Series.style["music_object_key"]` updated in the dev DB for series id 2 — Task 7's rebuild reads both.

- [ ] **Step 1: Generate the full-length track and save the series style**

Run (fill in the chosen `style` value and music prompt text from Task 5's pick — example values shown, replace them):

```bash
py -c "
from dotenv import load_dotenv
load_dotenv()
import os
from saas.db import init_session_factory
from saas.models import Series
from agent_video.music import generate_music
from saas.storage import save_series_music

CHOSEN_VOICE_STYLE = 0.6  # replace with Task 5's pick
CHOSEN_MUSIC_PROMPT = 'tense atmospheric horror drone, sparse deep bass pulses, building dread, no melody, no vocals, suitable as quiet background under spoken narration'  # replace with Task 5's pick
EPISODE_DURATION_MS = 543000  # from the v3 rebuild: 9:02.85 -> round up to nearest second * 1000

db = init_session_factory()()
try:
    series = db.query(Series).filter_by(id=2).one()
    content = generate_music(CHOSEN_MUSIC_PROMPT, EPISODE_DURATION_MS, os.environ['ELEVENLABS_API_KEY'])
    key = save_series_music(series.id, 'ep1_background.mp3', content)
    series.style = {**series.style, 'voice_style': CHOSEN_VOICE_STYLE, 'music_object_key': key}
    db.commit()
    print('music_object_key:', key)
    print('style:', series.style)
finally:
    db.close()
"
```

Reassigning `series.style` to a new dict (rather than mutating the existing dict in place with `series.style['voice_style'] = ...`) is required for SQLAlchemy to detect the change on a JSON column — in-place mutation is invisible to the ORM's change tracking without an explicit `flag_modified()` call, so a plain reassignment is the simpler, less error-prone option here.

- [ ] **Step 2: Verify**

```bash
py -c "
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Series

db = init_session_factory()()
try:
    series = db.query(Series).filter_by(id=2).one()
    print(series.style)
finally:
    db.close()
"
```

Expected: printed dict includes both `voice_style` (a float) and `music_object_key` (a string starting with `series/2/music`), alongside the pre-existing `voice_id`/`tts_provider`/`language` keys.

(No commit — dev-DB data change, same as the prior plan's Task 4.)

---

### Task 7: Rebuild EP1 and verify music + dramatic delivery

**Files:**
- None (reruns `run_build`, same pattern as the prior plan's Task 6).

**Interfaces:**
- Consumes: `saas.tasks.run_build(job_id, session_factory)` (existing, now emitting `style`-aware narration and downloading music when set).
- Produces: a new `episodes/6/output.mp4` in MinIO with background music mixed in.

- [ ] **Step 1: Short test build first (1-2 scenes) — standing user preference**

The engine-level short-test script used earlier this session (calling `build_scene_clip`/`build_episode` directly on 2-3 scenes) bypasses `run_build` entirely, which means it would also bypass Task 4's new music-download step. Since this task specifically needs to verify the music mix, build the short test through `run_build` itself, against a temporary duplicate 3-scene episode so the real episode-6 `Job`/`Episode` rows aren't touched:

```python
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Episode, Job, Scene
from saas.tasks import run_build

session_factory = init_session_factory()
db = session_factory()
try:
    ep6 = db.query(Episode).filter_by(id=6).one()
    scratch = Episode(
        user_id=ep6.user_id, series_id=ep6.series_id, title="scratch-short-test",
        description="", tags="", status="draft",
    )
    db.add(scratch)
    db.flush()
    for scene in sorted(ep6.scenes, key=lambda s: s.order_index)[:3]:
        db.add(Scene(
            episode_id=scratch.id, order_index=scene.order_index,
            narration_text=scene.narration_text, asset_object_key=scene.asset_object_key,
        ))
    db.commit()
    job = Job(episode_id=scratch.id, type="build", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id, scratch_id = job.id, scratch.id
finally:
    db.close()

run_build(job_id, session_factory)

db = session_factory()
try:
    job = db.query(Job).filter_by(id=job_id).one()
    scratch = db.query(Episode).filter_by(id=scratch_id).one()
    print("job status", job.status, job.error_message)
    print("output key", scratch.output_object_key)
finally:
    db.close()
```

Then download `episodes/<scratch_id>/output.mp4` from MinIO the same way as Task 6 Step 3 of the prior plan and listen/watch it. Confirm:
- The narration sounds more dramatic than the v3 build (informal A/B listen against `output_en_v3.mp4`).
- Background music is present, audible, and doesn't drown out narration (adjust `config["audio"]["music_volume"]` in `agent_video/config.py`, default `0.18`, if it's off-balance).

If either check fails, stop and fix before Step 2 — do not proceed to a full rebuild on a known-bad short test. Delete the scratch episode when done so it doesn't clutter the dev DB — `Query.delete()` is a bulk SQL delete that bypasses the ORM's `cascade="all, delete-orphan"`, so fetch the instance and use `Session.delete()` instead, which does cascade to its scenes:

```python
db = session_factory()
try:
    scratch = db.query(Episode).filter_by(id=scratch_id).one()
    db.delete(scratch)
    db.commit()
finally:
    db.close()
```

- [ ] **Step 2: Trigger the full rebuild**

```bash
py -c "
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Episode, Job
from saas.tasks import run_build

session_factory = init_session_factory()
db = session_factory()
try:
    episode = db.query(Episode).filter_by(id=6).one()
    episode.status = 'draft'
    job = Job(episode_id=6, type='build', status='queued')
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
finally:
    db.close()
print('job_id', job_id)
run_build(job_id, session_factory)
db = session_factory()
try:
    job = db.query(Job).filter_by(id=job_id).one()
    episode = db.query(Episode).filter_by(id=6).one()
    print('job status', job.status, job.error_message)
    print('episode status', episode.status, episode.output_object_key)
finally:
    db.close()
"
```

Expected: `job status done None` and `episode status built episodes/6/output.mp4`.

- [ ] **Step 3: Download and verify across the whole video**

```bash
docker compose exec -T minio mc cat local/whatif-assets/episodes/6/output.mp4 > "D:/Video/Seri 1/EP 1/output_en_v4.mp4"
```

Sample 8-10 timestamps spread across the full duration (same technique as the prior plan's Task 6 Step 3) and confirm for each: music is present and audible without drowning narration, delivery sounds more dramatic than v3, captions/backgrounds are still correct (regression check — Tasks 1-6 here didn't touch captions or the image catalog, so this should be unchanged from v3, but confirm nothing broke).

If any check fails, that is a new finding — stop, diagnose (is it a music volume issue → adjust `config["audio"]["music_volume"]` in `agent_video/config.py`; is it a missing file → check Task 6's `music_object_key` was actually saved), and fix before declaring the task done.

- [ ] **Step 4: Hand off to the user**

Open the file for the user and report what changed since v3 (music added, voice style value used) — not just "please check," since Step 3's review already happened.

(No commit — this task's artifact is the rebuilt video, not a code change.)

---

## Self-Review Notes

- **Spec coverage:** Roadmap Phase 1 item 1 (background music) → Tasks 3, 4, 5, 6, 7. Phase 1 item 2 (dramatic voice) → Tasks 1, 2, 5, 6, 7. Phases 2-3 of the roadmap are explicitly out of scope for this plan (separate future plans).
- **Placeholder scan:** `CHOSEN_VOICE_STYLE` / `CHOSEN_MUSIC_PROMPT` / `EPISODE_DURATION_MS` in Task 6 Step 1 are intentional fill-in-at-runtime values (only knowable after Task 5's user decision and after re-checking the v3 build's exact duration) — not unresolved requirements, same pattern as `REPLACE_WITH_SCENE_ID` in the prior plan.
- **Type/name consistency:** `Series.style` dict keys (`voice_style`, `music_object_key`) don't collide with existing keys (`voice_id`, `tts_provider`, `language`, `image_style_bible`) verified against `saas/models.py` and the prior plan's ledger. `ElevenLabsTTS`/`AzureTTS`/`get_tts_provider` signatures match `saas/tts_providers.py` as it exists after the prior plan's Task 1-6 (retry fix in `agent_video/tts.py` doesn't touch the `voice_settings` dict this plan modifies, confirmed by reading the current file before writing this plan).
