# EP1 Render Quality Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three rejected aspects of EP1's render — scene backgrounds being unreadable close-up crops of character/object cutouts, oversized captions colliding with in-image text, and an unvetted narrator voice — then rebuild EP1 and verify by sampling frames across the whole video.

**Architecture:** `analyze_script`'s asset-matching is restricted to `location`-kind (or previously AI-generated) series assets so it never again picks a character/object cutout as a full-frame background; scenes that would have matched a non-background asset instead get a freshly generated full-16:9-scene image. Captions get a smaller font plus an opaque background box (ASS `BorderStyle=3`) instead of just an outline. The narrator voice is picked by sourcing and comparing several English candidates, same process already used for Vietnamese.

**Tech Stack:** Python/FastAPI backend (`saas/`), the standalone `agent_video/` rendering engine, SQLAlchemy/Postgres, ElevenLabs + Azure TTS, OpenAI `gpt-image-1`, ffmpeg/libass for caption burn-in.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-episode-render-quality-fix-design.md` — follow its decisions exactly; do not add multi-layer overlay compositing (explicitly out of scope).
- Unit tests must never call real external APIs (Anthropic/OpenAI/ElevenLabs/Azure) — always monkeypatch, per existing convention in `tests/saas/`.
- Run backend tests with `python -m pytest tests/ -q` from `D:\Video\agent_video`.
- Local dev services (Postgres :5433, Redis, MinIO) are started with `docker compose up -d` from `D:\Video\agent_video`; `.env` already has working ANTHROPIC_API_KEY / OPENAI_API_KEY / ELEVENLABS_API_KEY / AZURE_SPEECH_KEY.
- Commit messages follow the existing `fix(scope): ...` / `feat(scope): ...` convention. Create a new commit per task.

---

### Task 1: Restrict `analyze_script` catalog to background-only assets

**Files:**
- Modify: `saas/routers/episodes.py:124-130`
- Modify: `saas/ai/script_analysis.py:14-26`
- Test: `tests/saas/test_script_analysis.py`

**Interfaces:**
- Consumes: `SeriesAsset.kind` (str: `"location"|"character"|"object"|"other"`), `SeriesAsset.source` (str: `"uploaded"|"generated"`) — existing model fields, `saas/models.py:47-59`.
- Produces: no new public interface — `analyze_episode_script` (the `/episodes/{id}/analyze-script` route) now sends a filtered catalog to `analyze_script`; behavior change only.

- [ ] **Step 1: Write the failing test**

Add to `tests/saas/test_script_analysis.py` (after `test_endpoint_replaces_scenes_and_copies_matched_object_key`):

```python
def test_endpoint_only_sends_location_and_generated_assets_to_ai(client, monkeypatch):
    headers = _auth(client)
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    ep_id = client.post(
        "/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers
    ).json()["id"]

    monkeypatch.setattr(
        "saas.routers.series.save_series_asset", lambda *a, **k: "series/1/assets/1.png"
    )

    def _upload(kind, name):
        return client.post(
            f"/series/{sid}/assets",
            files={"file": ("a.png", b"png-bytes", "image/png")},
            data={"kind": kind, "name": name, "description": name},
            headers=headers,
        ).json()

    location_asset = _upload("location", "bedroom")
    character_asset = _upload("character", "hero")
    object_asset = _upload("object", "flashlight")

    captured = {}

    def fake_analyze(script, language, asset_catalog):
        captured["catalog"] = asset_catalog
        return [{"narration_text": "One.", "asset_id": None, "asset_brief": "A scene"}]

    monkeypatch.setattr(episodes_router, "analyze_script", fake_analyze)

    client.post(f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers)

    sent_ids = {a["id"] for a in captured["catalog"]}
    assert location_asset["id"] in sent_ids
    assert character_asset["id"] not in sent_ids
    assert object_asset["id"] not in sent_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/saas/test_script_analysis.py::test_endpoint_only_sends_location_and_generated_assets_to_ai -v`
Expected: FAIL — `character_asset["id"] not in sent_ids` (or `object_asset`) assertion fails because the current code sends every asset regardless of kind.

- [ ] **Step 3: Filter the catalog in the router**

In `saas/routers/episodes.py`, replace lines 124-130:

```python
    series = episode.series
    style = series.style if series else {}
    assets = series.assets if series else []
    catalog = [
        {"id": a.id, "kind": a.kind, "name": a.name, "description": a.description}
        for a in assets
    ]
```

with:

```python
    series = episode.series
    style = series.style if series else {}
    assets = series.assets if series else []
    # Only full-scene backgrounds are valid matches — character/object/UI-mockup
    # assets were authored as small overlay pieces, not standalone 16:9 scenes,
    # and forcing them full-frame produces unreadable crops (see
    # docs/superpowers/specs/2026-07-14-episode-render-quality-fix-design.md).
    background_assets = [a for a in assets if a.kind == "location" or a.source == "generated"]
    catalog = [
        {"id": a.id, "kind": a.kind, "name": a.name, "description": a.description}
        for a in background_assets
    ]
```

Leave `assets_by_id = {a.id: a for a in assets}` (line 136, unchanged) — it still needs the full asset list for lookup by id; `analyze_script`'s own `valid_ids` check (in `saas/ai/script_analysis.py`) already rejects any id the AI returns that wasn't in the catalog it was sent, so a stray id can never resolve to a non-background asset.

- [ ] **Step 4: Update the system prompt wording**

In `saas/ai/script_analysis.py`, replace the `system` assignment (lines 14-26):

```python
    system = (
        "You split a narrated YouTube video script into visual scenes. "
        "Each scene is 1-4 sentences of narration shown over ONE still image. "
        f"The narration language is {language_name}.\n"
        f"Available images (the series asset catalog):\n{catalog_json}\n\n"
        "For each scene pick the best-matching asset id from the catalog, or null "
        "if none fits. When asset_id is null, write asset_brief: a detailed, "
        "self-contained ENGLISH image-generation prompt for the missing image "
        "(subject, setting, mood, composition). The image is generated at a 3:2 ratio "
        "then center-cropped to 16:9 video, trimming roughly the top and bottom 8% — "
        "keep faces and key subjects vertically centered, not near the top or bottom edge. "
        "Keep the narration text verbatim — do not rewrite it, only split it.\n"
        'Reply with ONLY JSON: {"scenes": [{"narration_text": str, '
        '"asset_id": int | null, "asset_brief": str | null}]}'
    )
```

with:

```python
    system = (
        "You split a narrated YouTube video script into visual scenes. "
        "Each scene is 1-4 sentences of narration shown over ONE still image. "
        f"The narration language is {language_name}.\n"
        f"Available background scenes (the series location catalog):\n{catalog_json}\n\n"
        "For each scene pick the best-matching background id from the catalog, or null "
        "if none fits — the catalog only contains full establishing-shot backgrounds, "
        "never close-ups of a single character or object. When asset_id is null, write "
        "asset_brief: a detailed, self-contained ENGLISH image-generation prompt for the "
        "missing image. The brief must describe a full wide scene (subject, setting, mood, "
        "composition) framed for 16:9 video — never a tight cutout of just a character, "
        "hand, or object with no surrounding environment. The image is generated at a 3:2 "
        "ratio then center-cropped to 16:9 video, trimming roughly the top and bottom 8% — "
        "keep faces and key subjects vertically centered, not near the top or bottom edge. "
        "Keep the narration text verbatim — do not rewrite it, only split it.\n"
        'Reply with ONLY JSON: {"scenes": [{"narration_text": str, '
        '"asset_id": int | null, "asset_brief": str | null}]}'
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/saas/test_script_analysis.py -v`
Expected: all tests PASS, including the new `test_endpoint_only_sends_location_and_generated_assets_to_ai`.

- [ ] **Step 6: Run the full backend suite and commit**

Run: `python -m pytest tests/ -q`
Expected: all pass (234+ tests).

```bash
git add saas/routers/episodes.py saas/ai/script_analysis.py tests/saas/test_script_analysis.py
git commit -m "fix(ai): restrict analyze-script catalog matching to background-only assets

character/object/UI-mockup assets were authored as small overlay pieces,
not standalone 16:9 scenes. analyze_script was picking them as full-frame
backgrounds, which the cover-crop pipeline then destroyed down to an
unreadable close-up. Only location-kind and previously-generated assets
are valid background matches now; everything else falls through to
generating a proper full-scene image."
```

---

### Task 2: Smaller caption font + opaque background box

**Files:**
- Modify: `agent_video/config.py:9-13`
- Modify: `agent_video/video_builder.py:64-66`
- Test: `tests/test_video_builder.py`

**Interfaces:**
- Consumes: `config["caption"]["font"]` / `config["caption"]["font_size"]` (existing `DEFAULT_CONFIG` shape, unchanged keys).
- Produces: no new public interface — `build_episode`'s ffmpeg `force_style` string changes; behavior change only (verified by inspecting the constructed command in tests, and by an actual render in Step 5).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_video_builder.py` (after `test_build_episode_applies_caption_font_config`):

```python
def test_build_episode_adds_caption_background_box(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    clip_paths = [str(tmp_path / "scene_01.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()
    episode = Episode(title="Test", description="", tags=[], scenes=[Scene(name="scene_01", asset="a.png", text="hi")])

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result) as run_mock, \
         patch("agent_video.video_builder.get_ffmpeg_exe", return_value="ffmpeg"):
        build_episode(episode, clip_paths, audio_paths, [2.0], video_dir, DEFAULT_CONFIG)

    final_cmd = " ".join(run_mock.call_args_list[-1][0][0])
    assert "BorderStyle=3" in final_cmd
    assert "BackColour=&H80000000" in final_cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_video_builder.py::test_build_episode_adds_caption_background_box -v`
Expected: FAIL — `BorderStyle=3` not found in the constructed ffmpeg command.

- [ ] **Step 3: Lower the default font size**

In `agent_video/config.py`, replace line 12:

```python
    "caption": {"font": "Arial", "font_size": 34},
```

with:

```python
    "caption": {"font": "Arial", "font_size": 26},
```

- [ ] **Step 4: Add the opaque background box to `force_style`**

In `agent_video/video_builder.py`, replace lines 64-66:

```python
    font = config["caption"]["font"]
    font_size = config["caption"]["font_size"]
    force_style = f"force_style='FontName={font},FontSize={font_size}'"
```

with:

```python
    font = config["caption"]["font"]
    font_size = config["caption"]["font_size"]
    # BorderStyle=3 draws an opaque box behind the text (BackColour) instead of
    # just an outline — shrinks the caption's visual weight and hides whatever
    # is underneath, including baked-in text in UI-mockup scene images.
    # BackColour is ASS &HAABBGGRR: AA=80 is ~50% transparent black.
    force_style = (
        f"force_style='FontName={font},FontSize={font_size},"
        f"BorderStyle=3,Outline=1,Shadow=0,BackColour=&H80000000,MarginV=40'"
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_video_builder.py -v`
Expected: all tests PASS, including the new `test_build_episode_adds_caption_background_box`.

- [ ] **Step 6: Verify visually with a real render**

Run this from `D:\Video\agent_video` (adjust the source PNG path to any local scene image) to render one clip with the new caption style and inspect a frame — do not skip this, the previous font-size tuning round was wrong when only reasoned about in the abstract:

```bash
python -c "
from agent_video.captions import build_srt
from agent_video.script_parser import Episode, Scene
from agent_video.image_builder import build_scene_clip
from agent_video.video_builder import build_episode
from agent_video.config import DEFAULT_CONFIG
import os

text = 'His name was Long, thirty-two years old, an office worker in a central district.'
scene = Scene(name='scene_00', asset='PATH_TO_ANY_LOCAL_PNG', text=text)
episode = Episode(title='t', description='', tags=[], scenes=[scene])
os.makedirs('/tmp/capcheck/output', exist_ok=True)
build_scene_clip(scene.asset, 10.0, '/tmp/capcheck/clip.mp4', '/tmp/capcheck/tmp', DEFAULT_CONFIG)
# fake a silent-audio-free build isn't supported by build_episode directly;
# instead burn captions directly for a quick visual check:
from imageio_ffmpeg import get_ffmpeg_exe
import subprocess
build_srt(episode, [10.0], '/tmp/capcheck/out.srt')
srt = '/tmp/capcheck/out.srt'.replace(':', '\\\\:')
font, size = DEFAULT_CONFIG['caption']['font'], DEFAULT_CONFIG['caption']['font_size']
style = f\"FontName={font},FontSize={size},BorderStyle=3,Outline=1,Shadow=0,BackColour=&H80000000,MarginV=40\"
subprocess.run([get_ffmpeg_exe(), '-y', '-i', '/tmp/capcheck/clip.mp4', '-vf', f\"subtitles='{srt}':force_style='{style}'\", '-frames:v', '1', '-update', '1', '/tmp/capcheck/frame.png'])
print('wrote /tmp/capcheck/frame.png')
"
```

Read `/tmp/capcheck/frame.png` and confirm: text is legible, box background is visibly darker than the image behind it, and the box does not dominate more than roughly the bottom quarter of the frame. If it still looks too heavy, adjust `font_size` (try 22-24) or `BackColour` alpha (try `&HA0000000` for more opaque) and re-render before moving on — do not proceed on a guess.

- [ ] **Step 7: Commit**

```bash
git add agent_video/config.py agent_video/video_builder.py tests/test_video_builder.py
git commit -m "fix(captions): shrink font and add opaque background box

Font-size tuning alone (34px, previous commit) still read as visually
heavy and didn't solve captions overlapping baked-in text in UI-mockup
scene images. Switch to BorderStyle=3 (opaque box) and drop the default
to 26px — verified by rendering an actual frame, not just computed."
```

---

### Task 3: Source and compare English narrator voices

**Files:**
- Create: `scripts/compare_tts_en.py`
- Create (output, gitignored by existing `videos/` pattern — verify `videos/` is in `.gitignore`; if not, do not commit generated mp3s): `videos/tts_compare_en/*.mp3`

**Interfaces:**
- Consumes: `saas.tts_providers.ElevenLabsTTS`, `saas.tts_providers.AzureTTS` (existing, `synthesize(text, out_path, voice, language)`).
- Produces: a set of `.mp3` sample files for the user to listen to and a `voice_id`/`provider` decision that Task 4 consumes.

- [ ] **Step 1: Confirm `videos/` is untracked (it is NOT gitignored)**

Run: `git check-ignore -v videos/tts_compare/azure_vi-VN-HoaiMyNeural.mp3`
Expected: no output, exit code 1 — `videos/` has no blanket `.gitignore` rule (only `videos/*/audio/`, `videos/*/output/` etc. are ignored, per the repo's `.gitignore`). The earlier Vietnamese comparison mp3s were never committed only because nothing ever `git add`ed them. This is fine: Step 6 below stages files explicitly by name (never `git add -A`/`.`), so generated mp3s won't be committed by accident — just don't change that habit.

- [ ] **Step 2: Query ElevenLabs' shared voice library for narration-style candidates**

Run this to list candidate voice IDs (requires `ELEVENLABS_API_KEY` in `.env`, already present):

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os, requests
resp = requests.get(
    'https://api.elevenlabs.io/v1/shared-voices',
    headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']},
    params={'category': 'professional', 'gender': 'male', 'language': 'en', 'use_cases': 'narrative_story', 'page_size': 10},
    timeout=30,
)
print(resp.status_code)
for v in resp.json().get('voices', [])[:10]:
    print(v['voice_id'], '|', v.get('name'), '|', v.get('description', '')[:80])
"
```

If this endpoint returns a 401/403 (shared-voices requires a paid tier on some accounts), fall back to listing the account's own available voices instead:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os, requests
resp = requests.get('https://api.elevenlabs.io/v1/voices', headers={'xi-api-key': os.environ['ELEVENLABS_API_KEY']}, timeout=30)
print(resp.status_code)
for v in resp.json().get('voices', []):
    print(v['voice_id'], '|', v.get('name'), '|', (v.get('labels') or {}))
"
```

From the output, pick 2-3 voice_ids that look like deep/narrator-style male voices (or match whatever the user asks for if they gave a reference in conversation). Note the chosen IDs — Step 4 uses them.

- [ ] **Step 3: Write the comparison script**

Create `scripts/compare_tts_en.py`:

```python
"""Synthesize the same English paragraph with several candidate narrator voices.

Usage (from D:\\Video\\agent_video, with .env loaded):
    py scripts/compare_tts_en.py

Configure candidates via env:
    ELEVENLABS_API_KEY + ELEVENLABS_COMPARE_VOICES_EN (comma-separated voice IDs,
        sourced via the shared-voices/voices query in the implementation plan)
    AZURE_SPEECH_KEY + AZURE_SPEECH_REGION           (voices are preset below)

Output: videos/tts_compare_en/<provider>_<voice>.mp3 — listen and pick a voice
for the series.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from saas.tts_providers import AzureTTS, ElevenLabsTTS  # noqa: E402

SAMPLE_EN = (
    "What if, one morning, the entire city woke up to find the internet had "
    "vanished completely? No messages, no maps, not a single line of news. "
    "Over the next three minutes, let's explore this terrifying but entirely "
    "possible scenario."
)

AZURE_EN_VOICES = ["en-US-GuyNeural", "en-US-ChristopherNeural"]

OUT_DIR = os.path.join("videos", "tts_compare_en")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    produced = []

    el_voices = [v.strip() for v in os.environ.get("ELEVENLABS_COMPARE_VOICES_EN", "").split(",") if v.strip()]
    if os.environ.get("ELEVENLABS_API_KEY") and el_voices:
        for voice in el_voices:
            path = os.path.join(OUT_DIR, f"elevenlabs_{voice}.mp3")
            print(f"ElevenLabs {voice} -> {path}")
            ElevenLabsTTS().synthesize(SAMPLE_EN, path, voice=voice, language="en")
            produced.append(path)
    else:
        print("Skipping ElevenLabs (set ELEVENLABS_API_KEY and ELEVENLABS_COMPARE_VOICES_EN)")

    if os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"):
        for voice in AZURE_EN_VOICES:
            path = os.path.join(OUT_DIR, f"azure_{voice}.mp3")
            print(f"Azure {voice} -> {path}")
            AzureTTS().synthesize(SAMPLE_EN, path, voice=voice, language="en")
            produced.append(path)
    else:
        print("Skipping Azure (set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)")

    print(f"\nDone. {len(produced)} file(s) in {OUT_DIR}. Listen and pick a voice.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run it with the candidate voice IDs from Step 2**

```bash
ELEVENLABS_COMPARE_VOICES_EN=<id1>,<id2>,<id3> python scripts/compare_tts_en.py
```

Expected: prints one line per synthesized file, ends with `Done. N file(s) in videos/tts_compare_en. Listen and pick a voice.`

- [ ] **Step 5: Open every produced file for the user and stop for their decision**

```bash
for f in videos/tts_compare_en/*.mp3; do start "" "$f"; done
```

This task is done when the user has told you which file/voice to use going forward — do not proceed to Task 4 without an explicit pick.

- [ ] **Step 6: Commit the script (not the generated audio)**

```bash
git add scripts/compare_tts_en.py
git status  # confirm videos/tts_compare_en/*.mp3 is NOT staged
git commit -m "feat(scripts): add English TTS voice comparison script

Mirrors scripts/compare_tts_vi.py — the ElevenLabs voice wired into the
series was never deliberately chosen and sounds wrong in both languages."
```

---

### Task 4: Apply the chosen voice to the series

**Files:**
- None (data-only change via a one-off script, mirrors how `language` was updated in the EP1 build script).

**Interfaces:**
- Consumes: the `voice_id` and `provider` (`"elevenlabs"` or `"azure"`) chosen in Task 3.
- Produces: `Series.style["voice_id"]` / `Series.style["tts_provider"]` updated in the dev DB for series id 2 — Task 6's rebuild reads this.

- [ ] **Step 1: Update the series style**

Run (fill in the chosen provider/voice from Task 3's outcome — example values shown, replace them):

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy.orm.attributes import flag_modified
from saas.db import init_session_factory
from saas.models import Series

db = init_session_factory()()
try:
    series = db.query(Series).filter_by(id=2).one()
    style = dict(series.style)
    style['tts_provider'] = 'elevenlabs'  # or 'azure' — from Task 3's pick
    style['voice_id'] = 'REPLACE_WITH_CHOSEN_VOICE_ID'
    series.style = style
    flag_modified(series, 'style')
    db.commit()
    print('updated:', series.style)
finally:
    db.close()
"
```

- [ ] **Step 2: Verify**

Run: `docker compose exec -T postgres psql -U whatif -d whatif -c "select style from series where id=2;"`
Expected: `voice_id` and `tts_provider` reflect the new choice.

(No commit — this is a dev-DB data change, not a code change.)

---

### Task 5: Regenerate scene images for non-background assets in EP1

**Files:**
- Create (scratch, not committed): a one-off script following the pattern of `build_ep1_en.py` used earlier in this session.

**Interfaces:**
- Consumes: `saas.ai.script_analysis.analyze_script` (now fixed by Task 1 to only match background assets), `saas.ai.image_provider.get_image_provider`, `saas.storage.save_series_asset` — all existing.
- Produces: updates `Scene.asset_object_key` (and creates new `SeriesAsset` rows with `source="generated"`) for every episode-6 scene that currently points at a non-background asset. Task 6 rebuilds using the result.

- [ ] **Step 1: Find which scenes are flagged**

Run (from `D:\Video\agent_video`, with `docker compose up -d` already running):

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Episode, SeriesAsset

db = init_session_factory()()
try:
    episode = db.query(Episode).filter_by(id=6).one()
    assets_by_key = {a.object_key: a for a in db.query(SeriesAsset).filter_by(series_id=episode.series_id).all()}
    for scene in episode.scenes:
        asset = assets_by_key.get(scene.asset_object_key)
        ok = asset and (asset.kind == 'location' or asset.source == 'generated')
        if not ok:
            print(scene.order_index, scene.id, scene.asset_object_key, asset.kind if asset else None)
finally:
    db.close()
"
```

Expected: a list of `order_index, scene_id, asset_object_key, kind` lines — these are the scenes Steps 2-3 fix. (Earlier manual inspection during the design phase found roughly two-thirds of the 37 scenes flagged this way — expect a similar count; if the count seems very different, re-check the catalog `kind`/`source` values before proceeding.)

- [ ] **Step 2: For each flagged scene, get a background-only brief from the fixed `analyze_script`**

For each `(order_index, scene_id, narration_text)` found in Step 1 (fetch `narration_text` too — extend the Step 1 query to print it, or re-query), run per scene:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Episode, Scene, SeriesAsset
from saas.ai.script_analysis import analyze_script

SCENE_ID = REPLACE_WITH_SCENE_ID

db = init_session_factory()()
try:
    scene = db.query(Scene).filter_by(id=SCENE_ID).one()
    episode = db.query(Episode).filter_by(id=scene.episode_id).one()
    series = episode.series
    background_assets = [a for a in series.assets if a.kind == 'location' or a.source == 'generated']
    catalog = [{'id': a.id, 'kind': a.kind, 'name': a.name, 'description': a.description} for a in background_assets]
    result = analyze_script(scene.narration_text, series.style.get('language', 'en'), catalog)
    item = result[0]
    assets_by_id = {a.id: a for a in series.assets}
    matched = assets_by_id.get(item['asset_id']) if item['asset_id'] else None
    if matched:
        scene.asset_object_key = matched.object_key
        scene.asset_brief = None
        print('matched existing background:', matched.name)
    else:
        scene.asset_brief = item['asset_brief']
        print('needs new image, brief:', item['asset_brief'])
    db.commit()
finally:
    db.close()
"
```

This calls the real (now-fixed) `analyze_script` on just that scene's narration text, so it can only return a location/generated asset id or a full-wide-scene brief — never a character/object cutout.

- [ ] **Step 3: Generate the image for every scene that got a brief (no existing match)**

For each scene from Step 2 that printed `needs new image`, generate and save its asset via the same logic `POST /episodes/{id}/scenes/{scene_id}/generate-asset` uses:

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
from saas.db import init_session_factory
from saas.models import Scene, SeriesAsset
from saas.ai.image_provider import get_image_provider
from saas.storage import save_series_asset

SCENE_ID = REPLACE_WITH_SCENE_ID

db = init_session_factory()()
try:
    scene = db.query(Scene).filter_by(id=SCENE_ID).one()
    episode = scene.episode
    series = episode.series
    style_bible = series.style.get('image_style_bible', '')
    prompt = scene.asset_brief if not style_bible else f'{scene.asset_brief}\n\nStyle: {style_bible}'
    content = get_image_provider().generate(prompt)
    asset = SeriesAsset(
        series_id=series.id, kind='other',
        name=f'ep{episode.id}-scene{scene.order_index + 1}',
        description=scene.asset_brief, source='generated',
    )
    db.add(asset)
    db.flush()
    asset.object_key = save_series_asset(series.id, asset.id, 'generated.png', content)
    scene.asset_object_key = asset.object_key
    db.commit()
    print('generated:', asset.object_key)
finally:
    db.close()
"
```

- [ ] **Step 4: Re-run Step 1's query to confirm zero flagged scenes remain**

Expected: no output lines (every scene now points at a `location` or `source="generated"` asset).

(No commit — dev-DB data change, same as Task 4.)

---

### Task 6: Rebuild EP1 and verify across the whole video

**Files:**
- None (reruns the existing `run_build` function via a one-off script, same pattern as earlier in this session).

**Interfaces:**
- Consumes: `saas.tasks.run_build(job_id, session_factory)` (existing).
- Produces: a new `episodes/6/output.mp4` in MinIO.

- [ ] **Step 1: Trigger a fresh build**

```bash
python -c "
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

- [ ] **Step 2: Download the output**

```bash
docker compose exec -T minio mc cat local/whatif-assets/episodes/6/output.mp4 > "D:/Video/Seri 1/EP 1/output_en_v3.mp4"
```

- [ ] **Step 3: Sample frames across the whole video, not just the start**

```bash
python -c "
from imageio_ffmpeg import get_ffmpeg_exe
import subprocess, os
ffmpeg = get_ffmpeg_exe()
r = subprocess.run([ffmpeg, '-i', 'D:/Video/Seri 1/EP 1/output_en_v3.mp4'], capture_output=True, text=True)
print(r.stderr[-500:])
os.makedirs('D:/Video/Seri 1/EP 1/verify_v3', exist_ok=True)
# duration printed above — pick ~10 timestamps spread evenly across it, e.g. for a 7min video:
for t in [10, 40, 80, 120, 160, 200, 250, 300, 350, 400]:
    subprocess.run([ffmpeg, '-y', '-ss', str(t), '-i', 'D:/Video/Seri 1/EP 1/output_en_v3.mp4', '-frames:v', '1', '-update', '1', f'D:/Video/Seri 1/EP 1/verify_v3/t{t}.png'], capture_output=True, text=True)
"
```

Adjust the timestamp list to actually span the printed duration (roughly evenly spaced, 8-10 points).

- [ ] **Step 4: Read every generated frame and check each one**

For each `D:/Video/Seri 1/EP 1/verify_v3/tNN.png`, confirm:
- The background image is recognizable (not a meaningless close-up crop or a checkerboard/broken sliver).
- The caption box is present, legible, and does not cover more than roughly the bottom quarter of the frame.
- No caption overlaps pre-existing text baked into the image.

If any frame fails a check, that is a new finding — stop, identify which scene/asset it corresponds to (cross-reference the timestamp against cumulative scene durations in the DB, same approach as Task 5 Step 1), and fix it before declaring the task done. Do not hand this to the user with known-bad frames.

- [ ] **Step 5: Clean up scratch files**

```bash
rm -rf "D:/Video/Seri 1/EP 1/verify_v3"
```

Keep `output_en_v3.mp4` (and remove the older `output_en_v2.mp4`/`output_preview.mp4` once the user confirms v3 is good, not before).

- [ ] **Step 6: Hand off to the user**

Open the file for the user (`start "" "D:/Video/Seri 1/EP 1/output_en_v3.mp4"`) and report what changed since the last version they saw (voice, caption style, which scenes got new background images) — not just "please check," since your own Step 4 review already happened.

(No commit — this task's artifact is the rebuilt video, not a code change. If Step 4 uncovers a code-level bug, fix it under a new task/commit before rebuilding again.)

---

## Self-Review Notes

- **Spec coverage:** Design decision #1-3 (catalog filtering) → Task 1. #4 (captions) → Task 2. #5 (voice) → Tasks 3-4. #6 (rollout: fix → identify → regenerate → voice → rebuild → verify) → Tasks 1-6 in order. "Ngoài phạm vi" (no multi-layer compositing, no fixing all 32 uploaded assets, no voice picker UI) — none of Tasks 1-6 build those.
- **Placeholder scan:** `REPLACE_WITH_SCENE_ID` / `REPLACE_WITH_CHOSEN_VOICE_ID` in Tasks 4-5 are intentional fill-in-at-runtime values (their correct values only exist after Task 1's discovery queries and Task 3's user decision run) — not unresolved requirements. Everything else is concrete.
- **Type/name consistency:** `Series.style` dict keys (`voice_id`, `tts_provider`, `language`, `image_style_bible`) match `saas/models.py` usage verified earlier in this session. `SeriesAsset.kind`/`source` string values match the DB dump taken during investigation (`location`/`character`/`object`/`other`, `uploaded`/`generated`).
