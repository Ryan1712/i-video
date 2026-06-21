# What If Video Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the local CLI video engine (per `docs/superpowers/specs/2026-06-21-video-engine-design.md`) that turns a user-written `script.md` + a folder of user-supplied images into a narrated, captioned, Ken-Burns-animated mp4, plus a separate confirmed YouTube upload step.

**Architecture:** Five already-drafted pure-logic modules (`script_parser`, `manifest`, `tts`, `image_builder`, `captions`) get test coverage and a config refactor; two new modules (`video_builder`, `youtube_uploader`) are added; a `cli.py` wires everything into four commands (`new`, `status`, `build`, `upload`). All ffmpeg/network calls are wrapped behind functions that take an injected config dict, so unit tests mock `subprocess.run`/`requests.post` and assert on the constructed command/payload rather than requiring real ffmpeg binaries or API keys.

**Tech Stack:** Python 3.11+, pytest, PyYAML, Pillow, requests, imageio-ffmpeg, google-auth-oauthlib, google-api-python-client.

## Global Constraints

- All CLI output is Vietnamese, step-numbered, uses ✓/✗ markers, and gives actionable hints on error (spec: "CLI surface" section) — not raw stack traces.
- One episode processed per invocation — no batch/queue logic in this engine (spec: "Scope (v1)").
- Caption granularity is one cue per scene (full narration text), never word-level (spec: "Scope (v1)").
- `upload` defaults to `privacyStatus=private`; changing it requires an explicit `--public`/`--unlisted` flag, and the user must type `yes` at a final confirmation prompt before the API call (spec: `youtube_uploader.py` section).
- Configurable values (resolution, fps, Ken Burns zoom/speed, music volume, caption font/size) live in `config.yaml` (global) with optional per-episode override — never hardcoded as module constants (spec: "Configuration").
- Secrets (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`) stay in `.env`, never in `config.yaml`.
- Any failure stops the pipeline immediately, naming the failing scene/step — never silently skip or guess (spec: "Error handling").

---

## File Structure

```
agent_video/
  config.py                 # NEW — load_config(), merges defaults + global + per-episode yaml
  script_parser.py          # EXISTING — unmodified, gets tests
  manifest.py                # EXISTING — unmodified, gets tests
  captions.py                 # EXISTING — unmodified, gets tests
  tts.py                       # EXISTING — unmodified, gets tests
  image_builder.py            # MODIFY — replace module constants WIDTH/HEIGHT/FPS with a `config` param
  video_builder.py            # NEW — concat + mux + burn srt + optional music mix
  youtube_uploader.py         # NEW — OAuth + upload + confirmation gate
  cli.py                      # NEW — new/status/build/upload commands
config.yaml                  # NEW — default config values
pyproject.toml                # NEW — pytest config (pythonpath)
SETUP.md                      # NEW — ElevenLabs + YouTube one-time setup guide
tests/
  conftest.py
  test_script_parser.py
  test_manifest.py
  test_captions.py
  test_config.py
  test_image_builder.py
  test_tts.py
  test_video_builder.py
  test_youtube_uploader.py
  test_cli.py
```

---

### Task 1: Test scaffolding + lock in `script_parser.py`

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_script_parser.py`
- Modify: `requirements.txt` (add `pytest>=7.4.0`)

**Interfaces:**
- Consumes: `agent_video.script_parser.parse_script(path: str) -> Episode`, `Episode(title, description, tags, scenes)`, `Scene(name, asset, text)`, `ScriptParseError` (all already defined in `agent_video/script_parser.py`).
- Produces: a `tmp_episode_dir` pytest fixture (in `conftest.py`) that other test files reuse to create a scratch episode folder.

- [ ] **Step 1: Add pytest to requirements and create pytest config**

Append to `D:/Video/agent_video/requirements.txt`:
```
pytest>=7.4.0
PyYAML>=6.0
```

Create `D:/Video/agent_video/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: pytest, PyYAML, and the existing deps install without error.

- [ ] **Step 3: Create the shared fixture**

Create `D:/Video/agent_video/tests/conftest.py`:
```python
import pytest


@pytest.fixture
def tmp_episode_dir(tmp_path):
    """A scratch episode folder: tmp_path/ep/ with assets/, audio/, output/ subfolders."""
    ep_dir = tmp_path / "ep"
    (ep_dir / "assets").mkdir(parents=True)
    (ep_dir / "audio").mkdir()
    (ep_dir / "output").mkdir()
    return ep_dir
```

- [ ] **Step 4: Write failing tests for `script_parser.py`**

Create `D:/Video/agent_video/tests/test_script_parser.py`:
```python
import pytest

from agent_video.script_parser import parse_script, ScriptParseError


def _write_script(path, content):
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_parses_title_description_tags_and_scenes(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: What If The Moon Disappeared
description: Khám phá điều gì xảy ra
tags: whatif, space, science

## scene_01
asset: hero_intro.png
text: What if one day, the moon just vanished?

## scene_02
asset: hero_shocked.png
text: The tides would stop almost instantly.
""",
    )

    episode = parse_script(script_path)

    assert episode.title == "What If The Moon Disappeared"
    assert episode.description == "Khám phá điều gì xảy ra"
    assert episode.tags == ["whatif", "space", "science"]
    assert len(episode.scenes) == 2
    assert episode.scenes[0].name == "scene_01"
    assert episode.scenes[0].asset == "hero_intro.png"
    assert episode.scenes[0].text == "What if one day, the moon just vanished?"
    assert episode.scenes[1].name == "scene_02"


def test_multiline_text_is_joined_with_spaces(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: Test
description:
tags:

## scene_01
asset: hero.png
text: Line one
continues here.
""",
    )

    episode = parse_script(script_path)

    assert episode.scenes[0].text == "Line one continues here."


def test_missing_title_raises(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """## scene_01
asset: hero.png
text: hi
""",
    )

    with pytest.raises(ScriptParseError, match="missing required frontmatter field 'title'"):
        parse_script(script_path)


def test_scene_missing_asset_raises(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: Test

## scene_01
text: hi
""",
    )

    with pytest.raises(ScriptParseError, match="scene 'scene_01' is missing required field 'asset'"):
        parse_script(script_path)


def test_no_scenes_raises(tmp_episode_dir):
    script_path = _write_script(tmp_episode_dir / "script.md", "title: Test\n")

    with pytest.raises(ScriptParseError, match="no scene blocks found"):
        parse_script(script_path)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_script_parser.py -v`
Expected: All 5 tests PASS (the existing `script_parser.py` implementation already satisfies these — this step locks the behavior with a regression net, no source changes expected).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt tests/conftest.py tests/test_script_parser.py
git commit -m "test: add pytest scaffolding and lock in script_parser behavior"
```

---

### Task 2: Lock in `manifest.py`

**Files:**
- Create: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `agent_video.manifest.build_manifest(episode, video_dir, assets_common_dir) -> dict`, `agent_video.manifest.write_manifest(manifest, video_dir) -> str`, `agent_video.script_parser.Episode`, `Scene` (Task 1).

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_manifest.py`:
```python
import json
import os

from agent_video.manifest import build_manifest, write_manifest
from agent_video.script_parser import Episode, Scene


def _episode(scenes):
    return Episode(title="Test Episode", description="", tags=[], scenes=scenes)


def test_all_assets_missing(tmp_episode_dir, tmp_path):
    episode = _episode([
        Scene(name="scene_01", asset="hero.png", text="hi"),
    ])
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is False
    assert manifest["assets"][0]["status"] == "missing"
    assert manifest["assets"][0]["found_at"] is None
    assert manifest["assets"][0]["scene_text"] == "hi"


def test_asset_found_in_local_assets_dir(tmp_episode_dir, tmp_path):
    (tmp_episode_dir / "assets" / "hero.png").write_bytes(b"fake-png")
    episode = _episode([Scene(name="scene_01", asset="hero.png", text="hi")])
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is True
    assert manifest["assets"][0]["status"] == "ok"
    assert manifest["assets"][0]["found_at"].endswith("hero.png")


def test_asset_found_in_assets_common_fallback(tmp_episode_dir, tmp_path):
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)
    with open(os.path.join(common_dir, "recurring_hero.png"), "wb") as f:
        f.write(b"fake-png")
    episode = _episode([Scene(name="scene_01", asset="recurring_hero.png", text="hi")])

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is True
    assert manifest["assets"][0]["status"] == "ok"


def test_write_manifest_creates_json_file(tmp_episode_dir):
    manifest = {"title": "Test", "ready": True, "assets": []}

    path = write_manifest(manifest, str(tmp_episode_dir))

    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == manifest
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_manifest.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_manifest.py
git commit -m "test: lock in manifest.py behavior"
```

---

### Task 3: Lock in `captions.py`

**Files:**
- Create: `tests/test_captions.py`

**Interfaces:**
- Consumes: `agent_video.captions.build_srt(episode, durations, out_path) -> str`, `Episode`, `Scene` (Task 1).

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_captions.py`:
```python
import pytest

from agent_video.captions import build_srt
from agent_video.script_parser import Episode, Scene


def test_build_srt_writes_sequential_cues(tmp_path):
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[
            Scene(name="scene_01", asset="a.png", text="First line."),
            Scene(name="scene_02", asset="b.png", text="Second line."),
        ],
    )
    out_path = str(tmp_path / "out.srt")

    build_srt(episode, [2.5, 3.0], out_path)

    content = open(out_path, encoding="utf-8").read()
    assert "1\n00:00:00,000 --> 00:00:02,500\nFirst line." in content
    assert "2\n00:00:02,500 --> 00:00:05,500\nSecond line." in content


def test_mismatched_durations_length_raises():
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[Scene(name="scene_01", asset="a.png", text="hi")],
    )

    with pytest.raises(ValueError, match="durations length must match"):
        build_srt(episode, [1.0, 2.0], "/tmp/unused.srt")
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_captions.py -v`
Expected: Both tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_captions.py
git commit -m "test: lock in captions.py behavior"
```

---

### Task 4: `config.py` + `config.yaml`

**Files:**
- Create: `agent_video/config.py`
- Create: `config.yaml`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `agent_video.config.DEFAULT_CONFIG: dict`, `agent_video.config.load_config(video_dir: str, project_root: str = ".") -> dict`. Returned dict shape: `{"video": {"width": int, "height": int, "fps": int}, "ken_burns": {"zoom_start": float, "zoom_end": float, "speed": float}, "audio": {"music_volume": float}, "caption": {"font": str, "font_size": int}}`. Task 5 (`image_builder.py`) and Task 7 (`video_builder.py`) consume this exact shape.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_config.py`:
```python
import os

from agent_video.config import load_config, DEFAULT_CONFIG


def test_load_config_returns_defaults_when_no_files(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config == DEFAULT_CONFIG


def test_global_config_overrides_defaults(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        f.write("video:\n  width: 1280\n  height: 720\n")

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config["video"]["width"] == 1280
    assert config["video"]["height"] == 720
    assert config["video"]["fps"] == DEFAULT_CONFIG["video"]["fps"]  # untouched key preserved


def test_per_episode_config_overrides_global(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        f.write("ken_burns:\n  speed: 0.001\n")
    with open(os.path.join(video_dir, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("ken_burns:\n  speed: 0.005\n")

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config["ken_burns"]["speed"] == 0.005
    assert config["ken_burns"]["zoom_end"] == DEFAULT_CONFIG["ken_burns"]["zoom_end"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_video.config'`.

- [ ] **Step 3: Implement `config.py`**

Create `D:/Video/agent_video/agent_video/config.py`:
```python
"""Load video/Ken Burns/audio/caption settings from config.yaml, with per-episode override."""
from __future__ import annotations

import os

import yaml

DEFAULT_CONFIG = {
    "video": {"width": 1920, "height": 1080, "fps": 30},
    "ken_burns": {"zoom_start": 1.0, "zoom_end": 1.15, "speed": 0.0008},
    "audio": {"music_volume": 0.18},
    "caption": {"font": "Arial", "font_size": 48},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(video_dir: str, project_root: str = ".") -> dict:
    config = DEFAULT_CONFIG

    global_path = os.path.join(project_root, "config.yaml")
    if os.path.isfile(global_path):
        config = _deep_merge(config, _load_yaml(global_path))

    local_path = os.path.join(video_dir, "config.yaml")
    if os.path.isfile(local_path):
        config = _deep_merge(config, _load_yaml(local_path))

    return config
```

- [ ] **Step 4: Create the default `config.yaml`**

Create `D:/Video/agent_video/config.yaml`:
```yaml
video:
  width: 1920
  height: 1080
  fps: 30
ken_burns:
  zoom_start: 1.0
  zoom_end: 1.15
  speed: 0.0008
audio:
  music_volume: 0.18
caption:
  font: Arial
  font_size: 48
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_video/config.py config.yaml tests/test_config.py
git commit -m "feat: add config.yaml loader with global + per-episode override"
```

---

### Task 5: Refactor `image_builder.py` to use config

**Files:**
- Modify: `agent_video/image_builder.py`
- Create: `tests/test_image_builder.py`

**Interfaces:**
- Consumes: `agent_video.config.DEFAULT_CONFIG` shape (Task 4).
- Produces: `agent_video.image_builder.build_scene_clip(asset_path: str, duration: float, out_path: str, tmp_dir: str, config: dict) -> None` (signature changed: added `config` param, removed implicit module constants). Task 7 (`video_builder.py`) calls this with the `config` dict from `load_config`.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_image_builder.py`:
```python
from unittest.mock import patch, MagicMock

from PIL import Image

from agent_video.config import DEFAULT_CONFIG
from agent_video.image_builder import build_scene_clip


def _make_test_image(path, width=400, height=300):
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(path)


def test_build_scene_clip_invokes_ffmpeg_with_configured_dimensions(tmp_path):
    asset_path = str(tmp_path / "hero.png")
    _make_test_image(asset_path)
    out_path = str(tmp_path / "output" / "hero.mp4")
    tmp_dir = str(tmp_path / "tmp")

    config = {
        "video": {"width": 640, "height": 360, "fps": 24},
        "ken_burns": {"zoom_start": 1.0, "zoom_end": 1.2, "speed": 0.002},
    }

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.image_builder.subprocess.run", return_value=fake_result) as run_mock:
        build_scene_clip(asset_path, duration=2.0, out_path=out_path, tmp_dir=tmp_dir, config=config)

    assert run_mock.called
    cmd = run_mock.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "s=640x360" in cmd_str
    assert "fps=24" in cmd_str
    assert "zoom+0.002" in cmd_str
    assert "1.2" in cmd_str
    assert out_path in cmd


def test_build_scene_clip_raises_on_ffmpeg_failure(tmp_path):
    asset_path = str(tmp_path / "hero.png")
    _make_test_image(asset_path)
    out_path = str(tmp_path / "output" / "hero.mp4")
    tmp_dir = str(tmp_path / "tmp")

    fake_result = MagicMock(returncode=1, stderr="ffmpeg exploded")
    with patch("agent_video.image_builder.subprocess.run", return_value=fake_result):
        try:
            build_scene_clip(asset_path, duration=2.0, out_path=out_path, tmp_dir=tmp_dir, config=DEFAULT_CONFIG)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "ffmpeg exploded" in str(e)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_image_builder.py -v`
Expected: FAIL — `build_scene_clip() got an unexpected keyword argument 'config'` (current signature has no `config` param).

- [ ] **Step 3: Replace `D:/Video/agent_video/agent_video/image_builder.py` in full**

```python
"""Turn a static scene asset into a silent video clip with a Ken Burns pan/zoom."""
from __future__ import annotations

import os
import subprocess

from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe


def _cover_resize(src_path: str, dst_path: str, width: int, height: int) -> None:
    """Resize+crop image to exactly width x height, preserving aspect ratio (cover)."""
    img = Image.open(src_path).convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = width / height

    if src_ratio > dst_ratio:
        new_height = height
        new_width = int(new_height * src_ratio)
    else:
        new_width = width
        new_height = int(new_width / src_ratio)

    img = img.resize((new_width, new_height), Image.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    img.save(dst_path)


def build_scene_clip(asset_path: str, duration: float, out_path: str, tmp_dir: str, config: dict) -> None:
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    width = config["video"]["width"]
    height = config["video"]["height"]
    fps = config["video"]["fps"]
    zoom_end = config["ken_burns"]["zoom_end"]
    speed = config["ken_burns"]["speed"]

    fitted_path = os.path.join(tmp_dir, f"_fitted_{os.path.basename(out_path)}.png")
    _cover_resize(asset_path, fitted_path, width, height)

    ffmpeg_exe = get_ffmpeg_exe()
    total_frames = max(int(duration * fps), 1)

    # Slow zoom-in (Ken Burns) over the duration of the clip.
    zoompan = (
        f"scale=8000:-1,"
        f"zoompan=z='min(zoom+{speed},{zoom_end})':d={total_frames}:s={width}x{height}:fps={fps}"
    )

    cmd = [
        ffmpeg_exe,
        "-y",
        "-loop",
        "1",
        "-i",
        fitted_path,
        "-vf",
        zoompan,
        "-t",
        str(duration),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed building clip for {asset_path}:\n{result.stderr[-2000:]}")

    os.remove(fitted_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_image_builder.py -v`
Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_video/image_builder.py tests/test_image_builder.py
git commit -m "refactor: make image_builder.py read dimensions/Ken Burns params from config"
```

---

### Task 6: Lock in `tts.py`

**Files:**
- Create: `tests/test_tts.py`

**Interfaces:**
- Consumes: `agent_video.tts.synthesize_scene(text, out_path, api_key, voice_id) -> None`, `agent_video.tts.get_audio_duration(path) -> float`, `agent_video.tts.TTSError` (already defined in `agent_video/tts.py`).

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_tts.py`:
```python
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_tts.py -v`
Expected: All 4 tests PASS (existing implementation already satisfies these).

- [ ] **Step 3: Commit**

```bash
git add tests/test_tts.py
git commit -m "test: lock in tts.py behavior"
```

---

### Task 7: `video_builder.py`

**Files:**
- Create: `agent_video/video_builder.py`
- Create: `tests/test_video_builder.py`

**Interfaces:**
- Consumes: `agent_video.image_builder.build_scene_clip(...)` (Task 5), `agent_video.captions.build_srt(...)` (existing), `agent_video.config` shape (Task 4).
- Produces: `agent_video.video_builder.build_episode(episode, scene_clip_paths: list[str], scene_audio_paths: list[str], durations: list[float], video_dir: str, config: dict) -> str`. Returns the path to the final mp4. Task 9 (`cli.py`) calls this after TTS + per-scene clip building are done.

This module assumes per-scene silent clips and per-scene audio files already exist (built by Tasks 5/6 inside the `cli.py` `build` command in Task 9) — its job is purely: concat clips, mux audio, burn captions, optionally mix in `music.mp3` if present in `video_dir`.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_video_builder.py`:
```python
import os
from unittest.mock import patch, MagicMock

from agent_video.config import DEFAULT_CONFIG
from agent_video.script_parser import Episode, Scene
from agent_video.video_builder import build_episode


def _episode():
    return Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[
            Scene(name="scene_01", asset="a.png", text="First line."),
            Scene(name="scene_02", asset="b.png", text="Second line."),
        ],
    )


def test_build_episode_runs_ffmpeg_without_music(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    clip_paths = [str(tmp_path / "scene_01.mp4"), str(tmp_path / "scene_02.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3"), str(tmp_path / "scene_02.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result) as run_mock:
        out_path = build_episode(
            _episode(), clip_paths, audio_paths, [2.5, 3.0], video_dir, DEFAULT_CONFIG
        )

    assert out_path == os.path.join(video_dir, "output", "episode.mp4")
    # last call is the final ffmpeg invocation
    final_cmd = " ".join(run_mock.call_args_list[-1][0][0])
    assert "subtitles=" in final_cmd
    assert "amix" not in final_cmd  # no music.mp3 present


def test_build_episode_mixes_music_when_present(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    open(os.path.join(video_dir, "music.mp3"), "wb").close()
    clip_paths = [str(tmp_path / "scene_01.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()

    episode = Episode(title="Test", description="", tags=[], scenes=[Scene(name="scene_01", asset="a.png", text="hi")])

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result) as run_mock:
        build_episode(episode, clip_paths, audio_paths, [2.0], video_dir, DEFAULT_CONFIG)

    final_cmd = " ".join(run_mock.call_args_list[-1][0][0])
    assert "amix" in final_cmd
    assert "0.18" in final_cmd  # DEFAULT_CONFIG music_volume


def test_build_episode_raises_on_ffmpeg_failure(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    clip_paths = [str(tmp_path / "scene_01.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()
    episode = Episode(title="Test", description="", tags=[], scenes=[Scene(name="scene_01", asset="a.png", text="hi")])

    fake_result = MagicMock(returncode=1, stderr="ffmpeg blew up")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result):
        try:
            build_episode(episode, clip_paths, audio_paths, [2.0], video_dir, DEFAULT_CONFIG)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "ffmpeg blew up" in str(e)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_video_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_video.video_builder'`.

- [ ] **Step 3: Implement `video_builder.py`**

Create `D:/Video/agent_video/agent_video/video_builder.py`:
```python
"""Concat per-scene clips, mux audio, burn captions, optionally mix in background music."""
from __future__ import annotations

import os
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe

from .captions import build_srt
from .script_parser import Episode


def _write_concat_list(clip_paths: list[str], list_path: str) -> None:
    with open(list_path, "w", encoding="utf-8") as f:
        for path in clip_paths:
            escaped = path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")


def build_episode(
    episode: Episode,
    scene_clip_paths: list[str],
    scene_audio_paths: list[str],
    durations: list[float],
    video_dir: str,
    config: dict,
) -> str:
    ffmpeg_exe = get_ffmpeg_exe()
    output_dir = os.path.join(video_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "episode.mp4")

    concat_list_path = os.path.join(output_dir, "_concat_list.txt")
    _write_concat_list(scene_clip_paths, concat_list_path)

    silent_concat_path = os.path.join(output_dir, "_silent_concat.mp4")
    concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c", "copy", silent_concat_path,
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed concatenating scene clips:\n{result.stderr[-2000:]}")

    audio_concat_list_path = os.path.join(output_dir, "_audio_concat_list.txt")
    _write_concat_list(scene_audio_paths, audio_concat_list_path)
    concat_audio_path = os.path.join(output_dir, "_concat_audio.mp3")
    audio_concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat", "-safe", "0", "-i", audio_concat_list_path,
        "-c", "copy", concat_audio_path,
    ]
    result = subprocess.run(audio_concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed concatenating scene audio:\n{result.stderr[-2000:]}")

    srt_path = os.path.join(output_dir, "captions.srt")
    build_srt(episode, durations, srt_path)
    srt_filter_path = srt_path.replace("\\", "/").replace(":", "\\:")

    music_path = os.path.join(video_dir, "music.mp3")
    has_music = os.path.isfile(music_path)

    final_cmd = [ffmpeg_exe, "-y", "-i", silent_concat_path, "-i", concat_audio_path]
    if has_music:
        music_volume = config["audio"]["music_volume"]
        final_cmd += ["-i", music_path]
        filter_complex = (
            f"[1:a]volume=1.0[narration];"
            f"[2:a]volume={music_volume}[music];"
            f"[narration][music]amix=inputs=2:duration=first[mixed_audio];"
            f"[0:v]subtitles='{srt_filter_path}'[vout]"
        )
        final_cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[mixed_audio]",
        ]
    else:
        final_cmd += [
            "-vf", f"subtitles='{srt_filter_path}'",
            "-map", "0:v", "-map", "1:a",
        ]
    final_cmd += ["-c:v", "libx264", "-c:a", "aac", "-shortest", out_path]

    result = subprocess.run(final_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed building final episode:\n{result.stderr[-2000:]}")

    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_video_builder.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_video/video_builder.py tests/test_video_builder.py
git commit -m "feat: add video_builder.py (concat + mux + burn captions + optional music mix)"
```

---

### Task 8: `youtube_uploader.py`

**Files:**
- Create: `agent_video/youtube_uploader.py`
- Create: `tests/test_youtube_uploader.py`

**Interfaces:**
- Consumes: `agent_video.script_parser.Episode` (Task 1's existing module).
- Produces: `agent_video.youtube_uploader.build_upload_body(episode: Episode, privacy: str) -> dict` (pure function, easy to test), `agent_video.youtube_uploader.get_authenticated_service(client_secret_path: str, token_path: str)` (wraps OAuth, mockable), `agent_video.youtube_uploader.upload_video(video_path: str, episode: Episode, privacy: str, client_secret_path: str, token_path: str) -> str` (returns the resulting YouTube video id), `agent_video.youtube_uploader.MissingClientSecretError`. Task 9 (`cli.py`) calls `upload_video` after printing the confirmation summary and reading a `yes` response from the user.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_youtube_uploader.py`:
```python
from unittest.mock import patch, MagicMock

import pytest

from agent_video.script_parser import Episode, Scene
from agent_video.youtube_uploader import (
    build_upload_body,
    upload_video,
    MissingClientSecretError,
)


def _episode():
    return Episode(
        title="What If The Moon Disappeared",
        description="Khám phá...",
        tags=["whatif", "space"],
        scenes=[Scene(name="scene_01", asset="a.png", text="hi")],
    )


def test_build_upload_body_defaults_to_private():
    body = build_upload_body(_episode(), privacy="private")

    assert body["snippet"]["title"] == "What If The Moon Disappeared"
    assert body["snippet"]["description"] == "Khám phá..."
    assert body["snippet"]["tags"] == ["whatif", "space"]
    assert body["status"]["privacyStatus"] == "private"


def test_build_upload_body_accepts_public_or_unlisted():
    body = build_upload_body(_episode(), privacy="public")
    assert body["status"]["privacyStatus"] == "public"


def test_upload_video_raises_without_client_secret(tmp_path):
    missing_secret_path = str(tmp_path / "client_secret.json")

    with pytest.raises(MissingClientSecretError, match="client_secret.json"):
        upload_video(
            video_path=str(tmp_path / "episode.mp4"),
            episode=_episode(),
            privacy="private",
            client_secret_path=missing_secret_path,
            token_path=str(tmp_path / "token.json"),
        )


def test_upload_video_calls_youtube_api_with_built_body(tmp_path):
    client_secret_path = str(tmp_path / "client_secret.json")
    open(client_secret_path, "w").close()
    video_path = str(tmp_path / "episode.mp4")
    open(video_path, "wb").close()

    fake_request = MagicMock()
    fake_request.execute.return_value = {"id": "abc123"}
    fake_videos = MagicMock()
    fake_videos.insert.return_value = fake_request
    fake_service = MagicMock()
    fake_service.videos.return_value = fake_videos

    with patch("agent_video.youtube_uploader.get_authenticated_service", return_value=fake_service):
        with patch("agent_video.youtube_uploader.MediaFileUpload") as media_mock:
            video_id = upload_video(
                video_path=video_path,
                episode=_episode(),
                privacy="private",
                client_secret_path=client_secret_path,
                token_path=str(tmp_path / "token.json"),
            )

    assert video_id == "abc123"
    call_kwargs = fake_videos.insert.call_args[1]
    assert call_kwargs["body"]["status"]["privacyStatus"] == "private"
    media_mock.assert_called_once_with(video_path, chunksize=-1, resumable=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_youtube_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_video.youtube_uploader'`.

- [ ] **Step 3: Implement `youtube_uploader.py`**

Create `D:/Video/agent_video/agent_video/youtube_uploader.py`:
```python
"""OAuth + YouTube Data API v3 upload, with a private-by-default confirmation gate."""
from __future__ import annotations

import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .script_parser import Episode

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class MissingClientSecretError(RuntimeError):
    pass


def build_upload_body(episode: Episode, privacy: str) -> dict:
    return {
        "snippet": {
            "title": episode.title,
            "description": episode.description,
            "tags": episode.tags,
        },
        "status": {"privacyStatus": privacy},
    }


def get_authenticated_service(client_secret_path: str, token_path: str):
    creds = None
    if os.path.isfile(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    episode: Episode,
    privacy: str,
    client_secret_path: str,
    token_path: str,
) -> str:
    if not os.path.isfile(client_secret_path):
        raise MissingClientSecretError(
            f"Không tìm thấy client_secret.json tại {client_secret_path}. "
            "Xem hướng dẫn ở SETUP.md mục YouTube."
        )

    service = get_authenticated_service(client_secret_path, token_path)
    body = build_upload_body(episode, privacy)
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return response["id"]
```

- [ ] **Step 4: Add the new dependencies already present in `requirements.txt`**

Confirm `google-auth-oauthlib` and `google-api-python-client` are already listed (they are, per the existing `requirements.txt`). No change needed here.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_youtube_uploader.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_video/youtube_uploader.py tests/test_youtube_uploader.py
git commit -m "feat: add youtube_uploader.py with private-by-default upload body"
```

---

### Task 9: `cli.py` — `new`, `status`, `build`, `upload`

**Files:**
- Create: `agent_video/cli.py`
- Create: `agent_video/__main__.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `agent_video.script_parser.parse_script` (Task 1), `agent_video.manifest.build_manifest/write_manifest/print_manifest_report` (Task 2), `agent_video.config.load_config` (Task 4), `agent_video.image_builder.build_scene_clip` (Task 5), `agent_video.tts.synthesize_scene/get_audio_duration` (Task 6), `agent_video.video_builder.build_episode` (Task 7), `agent_video.youtube_uploader.upload_video` (Task 8).
- Produces: `agent_video.cli.slugify(title: str) -> str`, `agent_video.cli.next_episode_number(videos_dir: str) -> int`, `agent_video.cli.cmd_new(title: str, videos_dir: str) -> str` (returns created episode dir path), `agent_video.cli.cmd_status(video_dir: str) -> dict` (returns the manifest), `agent_video.cli.cmd_build(video_dir: str) -> str | None` (returns output path, or `None` if assets were missing), `agent_video.cli.main(argv: list[str] | None = None) -> int` (entry point, returns process exit code).

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/test_cli.py`:
```python
import os
from unittest.mock import patch

from agent_video.cli import slugify, next_episode_number, cmd_new, cmd_status, cmd_build


def test_slugify_lowercases_and_dashes():
    assert slugify("What If The Moon Disappeared") == "what-if-the-moon-disappeared"
    assert slugify("  Extra   Spaces!! ") == "extra-spaces"


def test_next_episode_number_starts_at_1(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(videos_dir)

    assert next_episode_number(videos_dir) == 1


def test_next_episode_number_increments_past_existing(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(os.path.join(videos_dir, "ep01_foo"))
    os.makedirs(os.path.join(videos_dir, "ep03_bar"))

    assert next_episode_number(videos_dir) == 4


def test_cmd_new_creates_expected_structure(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(videos_dir)

    ep_dir = cmd_new("What If The Moon Disappeared", videos_dir)

    assert os.path.basename(ep_dir) == "ep01_what-if-the-moon-disappeared"
    assert os.path.isdir(os.path.join(ep_dir, "assets"))
    assert os.path.isdir(os.path.join(ep_dir, "audio"))
    assert os.path.isdir(os.path.join(ep_dir, "output"))
    assert os.path.isfile(os.path.join(ep_dir, "script.md"))
    content = open(os.path.join(ep_dir, "script.md"), encoding="utf-8").read()
    assert "title: What If The Moon Disappeared" in content
    assert "## scene_01" in content


def test_cmd_status_reports_missing_assets(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = cmd_status(ep_dir, assets_common_dir=common_dir)

    assert manifest["ready"] is False
    assert manifest["assets"][0]["asset"] == "hero.png"


def test_cmd_build_returns_none_when_assets_missing(tmp_path, capsys):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    result = cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    assert result is None
    captured = capsys.readouterr()
    assert "hero.png" in captured.out


def test_cmd_build_runs_full_pipeline_when_ready(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    open(os.path.join(ep_dir, "assets", "hero.png"), "wb").close()
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}):
        with patch("agent_video.cli.synthesize_scene") as synth_mock, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip") as clip_mock, \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")) as build_ep_mock:
            result = cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    assert result == os.path.join(ep_dir, "output", "episode.mp4")
    assert synth_mock.called
    assert clip_mock.called
    assert build_ep_mock.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent_video.cli'`.

- [ ] **Step 3: Implement `cli.py`**

Create `D:/Video/agent_video/agent_video/cli.py`:
```python
"""CLI entry point: new, status, build, upload commands."""
from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv

from .config import load_config
from .image_builder import build_scene_clip
from .manifest import build_manifest, print_manifest_report, write_manifest
from .script_parser import parse_script
from .tts import get_audio_duration, synthesize_scene
from .video_builder import build_episode
from .youtube_uploader import upload_video

SCRIPT_TEMPLATE = """title: {title}
description:
tags:

## scene_01
asset: hero_intro.png
text: Viết câu thoại đầu tiên ở đây.
"""


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def next_episode_number(videos_dir: str) -> int:
    existing = [d for d in os.listdir(videos_dir) if re.match(r"^ep(\d+)_", d)]
    numbers = [int(re.match(r"^ep(\d+)_", d).group(1)) for d in existing]
    return (max(numbers) + 1) if numbers else 1


def cmd_new(title: str, videos_dir: str) -> str:
    number = next_episode_number(videos_dir)
    slug = slugify(title)
    ep_dir = os.path.join(videos_dir, f"ep{number:02d}_{slug}")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write(SCRIPT_TEMPLATE.format(title=title))
    return ep_dir


def cmd_status(video_dir: str, assets_common_dir: str = "assets_common") -> dict:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    manifest = build_manifest(episode, video_dir, assets_common_dir)
    write_manifest(manifest, video_dir)
    print_manifest_report(manifest)
    return manifest


def cmd_build(video_dir: str, assets_common_dir: str = "assets_common", project_root: str = ".") -> str | None:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    manifest = build_manifest(episode, video_dir, assets_common_dir)
    write_manifest(manifest, video_dir)

    if not manifest["ready"]:
        print_manifest_report(manifest)
        return None

    print(f"Bước 1/4: Kiểm tra ảnh...                  ✓ Đủ {len(episode.scenes)}/{len(episode.scenes)} ảnh")

    config = load_config(video_dir, project_root=project_root)
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")

    audio_paths = []
    durations = []
    for scene in episode.scenes:
        audio_path = os.path.join(video_dir, "audio", f"{scene.name}.mp3")
        synthesize_scene(scene.text, audio_path, api_key, voice_id)
        duration = get_audio_duration(audio_path)
        audio_paths.append(audio_path)
        durations.append(duration)
    print(f"Bước 2/4: Tạo giọng đọc...                 ✓ {len(episode.scenes)} scene")

    clip_paths = []
    tmp_dir = os.path.join(video_dir, "output", "_tmp")
    asset_lookup = {item["asset"]: item["found_at"] for item in manifest["assets"]}
    for scene, duration in zip(episode.scenes, durations):
        clip_path = os.path.join(video_dir, "output", f"_clip_{scene.name}.mp4")
        build_scene_clip(asset_lookup[scene.asset], duration, clip_path, tmp_dir, config)
        clip_paths.append(clip_path)
    print("Bước 3/4: Dựng hình từng cảnh...           ✓ Xong")

    out_path = build_episode(episode, clip_paths, audio_paths, durations, video_dir, config)
    print("Bước 4/4: Ghép video + phụ đề + nhạc nền...✓ Xong")
    print(f"\nHoàn tất: {out_path}")
    return out_path


def cmd_upload(video_dir: str, privacy: str, client_secret_path: str, token_path: str) -> int:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    video_path = os.path.join(video_dir, "output", "episode.mp4")
    if not os.path.isfile(video_path):
        print(f"Chưa có {video_path} — hãy chạy 'build' trước.")
        return 1

    print("Sắp upload:")
    print(f"  Tiêu đề: {episode.title}")
    print(f"  Chế độ:  {privacy}")
    print(f"  File:    {video_path}\n")
    answer = input("Xác nhận đăng video này lên YouTube? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Đã hủy, không upload.")
        return 1

    video_id = upload_video(video_path, episode, privacy, client_secret_path, token_path)
    print(f"Đã upload: https://youtu.be/{video_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="agent_video")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("title")
    new_parser.add_argument("--videos-dir", default="videos")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("video_dir")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("video_dir")

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("video_dir")
    upload_parser.add_argument("--public", action="store_true")
    upload_parser.add_argument("--unlisted", action="store_true")
    upload_parser.add_argument("--client-secret", default="client_secret.json")
    upload_parser.add_argument("--token-path", default=None)

    args = parser.parse_args(argv)

    if args.command == "new":
        ep_dir = cmd_new(args.title, args.videos_dir)
        print(f"Đã tạo: {ep_dir}")
        return 0

    if args.command == "status":
        cmd_status(args.video_dir)
        return 0

    if args.command == "build":
        result = cmd_build(args.video_dir)
        return 0 if result else 1

    if args.command == "upload":
        privacy = "public" if args.public else ("unlisted" if args.unlisted else "private")
        token_path = args.token_path or os.path.join(args.video_dir, ".yt_token.json")
        return cmd_upload(args.video_dir, privacy, args.client_secret, token_path)

    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create the package entry point**

Create `D:/Video/agent_video/agent_video/__main__.py`:
```python
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Add `python-dotenv` usage check**

Confirm `python-dotenv` is already in `requirements.txt` (it is). No change needed.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: All tests across every file (Tasks 1–9) PASS.

- [ ] **Step 8: Commit**

```bash
git add agent_video/cli.py agent_video/__main__.py tests/test_cli.py
git commit -m "feat: add cli.py with new/status/build/upload commands"
```

---

### Task 10: `SETUP.md` + manual end-to-end verification

**Files:**
- Create: `SETUP.md`

**Interfaces:** none (documentation + manual verification task).

- [ ] **Step 1: Write `SETUP.md`**

Create `D:/Video/agent_video/SETUP.md`:
```markdown
# Setup (one-time)

## 1. ElevenLabs (voice)
1. Go to https://elevenlabs.io, sign in, open Settings → API Keys.
2. Create an API key, copy it into `.env` as `ELEVENLABS_API_KEY=...`.
3. Pick a voice (or clone your own) under Voices, copy its Voice ID into `.env` as `ELEVENLABS_VOICE_ID=...`.

## 2. YouTube (upload)
1. Go to https://console.cloud.google.com, create a new project.
2. Under "APIs & Services" → "Library", search for "YouTube Data API v3" and enable it.
3. Under "APIs & Services" → "Credentials", create an "OAuth Client ID" of type "Desktop app".
4. Download the resulting JSON and save it as `client_secret.json` in this project's root folder.
5. The first time you run `python -m agent_video upload <video_dir>`, a browser window opens asking you to log in and approve access — do this once. A token is cached afterward so you won't need to repeat this step.

## 3. Install dependencies
```
pip install -r requirements.txt
```

## 4. Try it
```
python -m agent_video new "What If The Moon Disappeared"
# edit videos/ep01_.../script.md, add required images to its assets/ folder
python -m agent_video status videos/ep01_what-if-the-moon-disappeared
python -m agent_video build videos/ep01_what-if-the-moon-disappeared
python -m agent_video upload videos/ep01_what-if-the-moon-disappeared
```
```

- [ ] **Step 2: Commit**

```bash
git add SETUP.md
git commit -m "docs: add SETUP.md for ElevenLabs and YouTube one-time setup"
```

- [ ] **Step 3: Manual end-to-end smoke test (requires a real ElevenLabs API key; YouTube upload is optional/skippable)**

Run, from `D:/Video/agent_video`:
```
python -m agent_video new "Test Episode"
```
Expected: prints `Đã tạo: videos/ep01_test-episode`.

Open `videos/ep01_test-episode/script.md`, change the single scene's `text:` to a short real sentence, keep `asset: hero_intro.png`. Then, using any image editor or a one-line Python script, create a placeholder 1920x1080 PNG at `videos/ep01_test-episode/assets/hero_intro.png`:
```
python -c "from PIL import Image; Image.new('RGB', (1920, 1080), (50, 80, 120)).save('videos/ep01_test-episode/assets/hero_intro.png')"
```

Add real credentials to `.env` (see `SETUP.md` step 1), then run:
```
python -m agent_video build videos/ep01_test-episode
```
Expected: step-by-step ✓ output ending in `Hoàn tất: videos/ep01_test-episode/output/episode.mp4`. Open that file and confirm: narrated audio plays, the burned-in caption matches the scene text, and the image has a visible slow zoom (Ken Burns).

(Optional) To test the upload path without a real channel upload, run `python -m agent_video upload videos/ep01_test-episode` with no `client_secret.json` present and confirm it prints the actionable "client_secret.json not found" message and exits non-zero, per the spec's error-handling requirement.

---

## Self-Review Notes

- **Spec coverage:** script_parser/manifest/captions/tts behaviors locked with tests (Tasks 1–3, 6); config.yaml externalization (Task 4) and image_builder refactor to consume it (Task 5) cover "Configuration"; video_builder (Task 7) covers concat/mux/burn/music; youtube_uploader (Task 8) covers private-default + confirmation gate (confirmation prompt itself lives in `cmd_upload` in `cli.py`, Task 9, since it's a CLI-level concern, not a library concern); cli.py (Task 9) covers all four commands and Vietnamese step-numbered ✓ output; SETUP.md + manual verification (Task 10) covers the one-time setup docs and spec's "Verification" section.
- **Placeholder scan:** no TBD/TODO; every step has runnable code.
- **Type consistency:** `build_scene_clip` signature (`asset_path, duration, out_path, tmp_dir, config`) defined in Task 5 is used identically in Task 9's `cmd_build`. `build_episode` signature (`episode, scene_clip_paths, scene_audio_paths, durations, video_dir, config`) defined in Task 7 matches its call in Task 9. `load_config(video_dir, project_root)` defined in Task 4 matches its call in Task 9.
