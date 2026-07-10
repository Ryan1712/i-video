# Phase 1 (v3): AI Brain + EP 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app its AI brain — script generation to a target duration, scene splitting with asset matching, in-tool image generation for missing assets, a TTS provider interface with a Vietnamese voice comparison — plus the frontend flow, then produce real Episode 1 with the existing ffmpeg pipeline.

**Architecture:** Spec is `docs/superpowers/specs/2026-07-10-product-vision-v3-design.md`. This plan REPLACES Tasks 4-8 of `2026-07-04-phase1-series-script-agent.md` (its Tasks 1-3 — Series/SeriesAsset models, series router, episode linking — are already merged on branch `phase1-series-agent` and are used as-is). New `saas/ai/` package holds the Anthropic client wrapper, script generation, script analysis, and the image provider. New `saas/tts_providers.py` abstracts TTS. Three new endpoints on the episodes router. Frontend gains Series pages and a script-first episode flow. Render pipeline stays the existing ffmpeg build task.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic, Celery (touched only in Task 6), `anthropic` Python SDK, OpenAI Images REST API (via `requests`), Azure Speech REST API (via `requests`), Next.js 14 App Router, Jest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-10-product-vision-v3-design.md`.
- Work on branch `phase1-series-agent` in `D:\Video\agent_video`.
- Run backend tests with `py -m pytest tests/saas/<file> -v` from `D:\Video\agent_video`. Tests use the in-memory SQLite fixtures in `tests/saas/conftest.py` — never a real Postgres. Frontend tests: `npm test` from `D:\Video\agent_video\frontend`.
- LLM model ID comes from env `ANTHROPIC_MODEL`, default **`claude-sonnet-5`**. NEVER hardcode a model ID at a call site, and never a date-suffixed variant.
- API error codes are stable strings (`ERR_...`) in `detail`; frontend owns translation.
- Ownership checks return 404 (not 403) for other users' resources, matching `_get_owned_episode_or_404` in `saas/routers/episodes.py`.
- There is no migration tool yet. New COLUMNS on existing tables need the manual `ALTER TABLE` statements in Task 1 Step 6 (dev DB only, Postgres on port 5433).
- Frontend calls go through the `/api` proxy (`frontend/src/lib/api.ts`); multipart uploads use raw `fetch("/api/...")` with the Bearer token, NOT `http://localhost:8000`.
- Commit messages follow the existing `feat(scope): ...` convention.
- Unit tests must never call real external APIs (Anthropic/OpenAI/ElevenLabs/Azure) — always monkeypatch.

---

### Task 1: DB columns + schemas (episode script fields, asset source)

**Files:**
- Modify: `saas/models.py`
- Modify: `saas/schemas.py`
- Test: `tests/saas/test_v3_models.py`

**Interfaces:**
- Produces: `Episode.brief: str` (default ""), `Episode.script: str` (default ""), `Episode.target_duration_sec: int | None`; `SeriesAsset.source: str` (default "uploaded", values `uploaded|generated`).
- Produces: `EpisodeIn` gains `brief: str = ""`, `target_duration_sec: int | None = None`; `EpisodeOut` gains `brief: str`, `script: str`, `target_duration_sec: int | None`; `SeriesAssetOut` gains `source: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/saas/test_v3_models.py`:

```python
from saas.models import Episode, Series, SeriesAsset, User


def _make_user(db_session, email="owner@example.com"):
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def test_episode_has_script_fields(db_session):
    user = _make_user(db_session)
    episode = Episode(
        user_id=user.id,
        title="EP1",
        brief="Zombie outbreak starts in a small town",
        script="Full narration text...",
        target_duration_sec=480,
    )
    db_session.add(episode)
    db_session.commit()

    loaded = db_session.query(Episode).one()
    assert loaded.brief.startswith("Zombie")
    assert loaded.script == "Full narration text..."
    assert loaded.target_duration_sec == 480


def test_episode_script_fields_default_empty(db_session):
    user = _make_user(db_session)
    db_session.add(Episode(user_id=user.id, title="EP1"))
    db_session.commit()
    loaded = db_session.query(Episode).one()
    assert loaded.brief == ""
    assert loaded.script == ""
    assert loaded.target_duration_sec is None


def test_series_asset_source_defaults_to_uploaded(db_session):
    user = _make_user(db_session)
    series = Series(user_id=user.id, name="S1")
    series.assets.append(SeriesAsset(kind="character", name="hero"))
    db_session.add(series)
    db_session.commit()
    assert db_session.query(SeriesAsset).one().source == "uploaded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_v3_models.py -v`
Expected: FAIL with `TypeError: 'brief' is an invalid keyword argument for Episode`

- [ ] **Step 3: Add the columns**

In `saas/models.py`, inside `class Episode`, after the `tags` line, add:

```python
    brief: Mapped[str] = mapped_column(Text, default="")
    script: Mapped[str] = mapped_column(Text, default="")
    target_duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Inside `class SeriesAsset`, after the `kind` line, add:

```python
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
```

- [ ] **Step 4: Update the schemas**

In `saas/schemas.py`:

In `EpisodeIn`, after `series_id: int | None = None`, add:

```python
    brief: str = ""
    target_duration_sec: int | None = None
```

In `EpisodeOut`, after `series_id: int | None = None`, add:

```python
    brief: str = ""
    script: str = ""
    target_duration_sec: int | None = None
```

In `SeriesAssetOut`, after `object_key: str | None`, add:

```python
    source: str = "uploaded"
```

In `saas/routers/episodes.py` `create_episode`, pass the new fields when constructing the Episode (after `series_id=payload.series_id,`):

```python
        brief=payload.brief,
        target_duration_sec=payload.target_duration_sec,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_v3_models.py tests/saas/test_episodes_routes.py tests/saas/test_series_routes.py -v`
Expected: all PASS

- [ ] **Step 6: Update the dev database (manual ALTER, dev only)**

Run (adjust password via `.env` if needed):

```bash
docker compose exec -T postgres psql -U whatif -d whatif -c "
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS brief TEXT NOT NULL DEFAULT '';
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS script TEXT NOT NULL DEFAULT '';
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS target_duration_sec INTEGER;
ALTER TABLE series_assets ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'uploaded';
"
```

If the postgres service name or credentials differ, check `docker-compose.yml`. If the DB is not running, skip — `create_all` covers fresh DBs; rerun this before manual testing.

- [ ] **Step 7: Commit**

```bash
git add saas/models.py saas/schemas.py saas/routers/episodes.py tests/saas/test_v3_models.py
git commit -m "feat(models): add episode brief/script/target_duration and series_asset source"
```

---

### Task 2: Anthropic client wrapper (`saas/ai/client.py`)

**Files:**
- Create: `saas/ai/__init__.py` (empty)
- Create: `saas/ai/client.py`
- Modify: `requirements.txt`
- Test: `tests/saas/test_ai_client.py`

**Interfaces:**
- Produces: `AIError(RuntimeError)`; `generate_json(system: str, user_message: str, max_tokens: int = 8192) -> dict` — calls Claude once, parses the response as JSON (tolerating ``` fences); on parse failure retries ONCE appending the parse error; then raises `AIError`. Model from env `ANTHROPIC_MODEL` (default `claude-sonnet-5`).

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_ai_client.py`:

```python
import pytest

import saas.ai.client as ai_client
from saas.ai.client import AIError, generate_json


class FakeContent:
    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, text):
        self.content = [FakeContent(text)]


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.replies.pop(0))


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def test_returns_parsed_json(monkeypatch):
    fake = FakeAnthropic(['{"script": "hello"}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    assert generate_json("sys", "user") == {"script": "hello"}


def test_strips_markdown_fences(monkeypatch):
    fake = FakeAnthropic(['```json\n{"a": 1}\n```'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    assert generate_json("sys", "user") == {"a": 1}


def test_retries_once_then_raises(monkeypatch):
    fake = FakeAnthropic(["not json", "still not json"])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    with pytest.raises(AIError):
        generate_json("sys", "user")
    assert len(fake.messages.calls) == 2
    # The retry message must mention the previous failure.
    assert "not valid JSON" in fake.messages.calls[1]["messages"][0]["content"]


def test_model_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
    fake = FakeAnthropic(['{"ok": true}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    generate_json("sys", "user")
    assert fake.messages.calls[0]["model"] == "claude-test-model"


def test_default_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    fake = FakeAnthropic(['{"ok": true}'])
    monkeypatch.setattr(ai_client, "_client", lambda: fake)
    generate_json("sys", "user")
    assert fake.messages.calls[0]["model"] == "claude-sonnet-5"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_ai_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.ai'`

- [ ] **Step 3: Install the SDK and write the module**

Append to `requirements.txt`:

```
anthropic>=0.40.0
```

Run: `py -m pip install "anthropic>=0.40.0"`

Create empty `saas/ai/__init__.py`, then `saas/ai/client.py`:

```python
"""Thin wrapper around the Anthropic SDK: one call, JSON out, one retry on bad JSON."""
from __future__ import annotations

import json
import os


class AIError(RuntimeError):
    pass


def _client():
    import anthropic

    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -3]
    return json.loads(cleaned)


def generate_json(system: str, user_message: str, max_tokens: int = 8192) -> dict:
    client = _client()
    message = user_message
    last_error = None
    for _ in range(2):
        response = client.messages.create(
            model=_model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        text = response.content[0].text
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, IndexError) as e:
            last_error = e
            message = (
                f"{user_message}\n\nYour previous reply was not valid JSON "
                f"({e}). Reply with ONLY the JSON object, no prose, no fences."
            )
    raise AIError(f"Model did not return valid JSON after retry: {last_error}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_ai_client.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add saas/ai/__init__.py saas/ai/client.py requirements.txt tests/saas/test_ai_client.py
git commit -m "feat(ai): add Anthropic client wrapper with JSON parsing and one retry"
```

---

### Task 3: Script generation module + endpoint

**Files:**
- Create: `saas/ai/script_generation.py`
- Modify: `saas/schemas.py`
- Modify: `saas/routers/episodes.py`
- Test: `tests/saas/test_script_generation.py`

**Interfaces:**
- Consumes: `generate_json` from Task 2; `_get_owned_episode_or_404` from `saas/routers/episodes.py`.
- Produces: `generate_script(brief: str, target_duration_sec: int, language: str, series_name: str = "", series_description: str = "") -> str` (raises `AIError`); schemas `GenerateScriptIn(brief: str, target_duration_sec: int)`, `ScriptOut(script: str)`; endpoint `POST /episodes/{id}/generate-script` → 200 `ScriptOut`, stores `episode.brief/target_duration_sec/script`; 502 `ERR_SCRIPT_GENERATION_FAILED` on `AIError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_script_generation.py`:

```python
import pytest
from fastapi.testclient import TestClient

import saas.ai.script_generation as sg
import saas.routers.episodes as episodes_router
from saas.ai.client import AIError
from saas.db import get_db
from saas.main import app


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="owner@example.com"):
    response = client.post("/auth/signup", json={"email": email, "password": "pw12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_word_target_scales_with_duration_and_language():
    assert sg._target_words(480, "en") == 480 // 60 * 150
    assert sg._target_words(480, "vi") == 480 // 60 * 160


def test_generate_script_builds_prompt_and_returns_text(monkeypatch):
    captured = {}

    def fake_generate_json(system, user_message, max_tokens=8192):
        captured["system"] = system
        captured["user"] = user_message
        return {"script": "Once upon a time..."}

    monkeypatch.setattr(sg, "generate_json", fake_generate_json)
    script = sg.generate_script("zombies attack", 480, "en", "What If", "zombie series")
    assert script == "Once upon a time..."
    assert "zombies attack" in captured["user"]
    assert "1200 words" in captured["user"]  # 8 min * 150 wpm
    assert "English" in captured["system"]


def test_generate_script_rejects_missing_script_key(monkeypatch):
    monkeypatch.setattr(sg, "generate_json", lambda *a, **k: {"wrong": 1})
    with pytest.raises(AIError):
        sg.generate_script("b", 60, "en")


def test_endpoint_stores_fields_and_returns_script(client, monkeypatch):
    monkeypatch.setattr(
        episodes_router, "generate_script", lambda **kwargs: "Generated script."
    )
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "zombie outbreak", "target_duration_sec": 480},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["script"] == "Generated script."

    ep = client.get(f"/episodes/{ep_id}", headers=headers).json()
    assert ep["brief"] == "zombie outbreak"
    assert ep["target_duration_sec"] == 480
    assert ep["script"] == "Generated script."


def test_endpoint_maps_aierror_to_502(client, monkeypatch):
    def boom(**kwargs):
        raise AIError("bad json")

    monkeypatch.setattr(episodes_router, "generate_script", boom)
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "b", "target_duration_sec": 60},
        headers=headers,
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "ERR_SCRIPT_GENERATION_FAILED"


def test_endpoint_is_owner_scoped(client, monkeypatch):
    monkeypatch.setattr(episodes_router, "generate_script", lambda **kwargs: "x")
    headers_a = _auth(client, "a@example.com")
    headers_b = _auth(client, "b@example.com")
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers_a).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "b", "target_duration_sec": 60},
        headers=headers_b,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_script_generation.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` on `saas.ai.script_generation`

- [ ] **Step 3: Write the module**

Create `saas/ai/script_generation.py`:

```python
"""Generate a full narration script from a brief, sized to a target duration."""
from __future__ import annotations

from .client import AIError, generate_json

# Approximate TTS speaking rates (words per minute) per language.
WORDS_PER_MINUTE = {"vi": 160, "en": 150}
LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def _target_words(target_duration_sec: int, language: str) -> int:
    wpm = WORDS_PER_MINUTE.get(language, 150)
    return max(1, target_duration_sec // 60) * wpm


def generate_script(
    brief: str,
    target_duration_sec: int,
    language: str,
    series_name: str = "",
    series_description: str = "",
) -> str:
    words = _target_words(target_duration_sec, language)
    language_name = LANGUAGE_NAMES.get(language, language)
    system = (
        "You are a professional scriptwriter for narrated YouTube storytelling "
        f"videos. Write in {language_name}. The script is read aloud by a single "
        "narrator: write ONLY the spoken narration — no scene headings, no camera "
        "directions, no speaker labels. Hook the viewer in the first two sentences. "
        'Reply with ONLY a JSON object: {"script": "<full narration>"}'
    )
    user = (
        f"Series: {series_name or '(standalone)'}\n"
        f"Series description: {series_description or '(none)'}\n"
        f"Episode idea/brief (may already be a partial script — expand it):\n{brief}\n\n"
        f"Target length: about {words} words "
        f"(≈{target_duration_sec // 60} minutes of narration)."
    )
    result = generate_json(system, user, max_tokens=16384)
    script = result.get("script")
    if not isinstance(script, str) or not script.strip():
        raise AIError("Model reply missing non-empty 'script' string")
    return script.strip()
```

- [ ] **Step 4: Add schemas and endpoint**

In `saas/schemas.py`, after `SceneOut`, add:

```python
class GenerateScriptIn(BaseModel):
    brief: str
    target_duration_sec: int


class ScriptOut(BaseModel):
    script: str
```

In `saas/routers/episodes.py`:

Add imports:

```python
from ..ai.client import AIError
from ..ai.script_generation import generate_script
```

Extend the schemas import line with `GenerateScriptIn, ScriptOut`.

Add the endpoint after `get_episode`:

```python
@router.post("/{episode_id}/generate-script", response_model=ScriptOut)
def generate_episode_script(
    episode_id: int,
    payload: GenerateScriptIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScriptOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    style = episode.series.style if episode.series else {}
    try:
        script = generate_script(
            brief=payload.brief,
            target_duration_sec=payload.target_duration_sec,
            language=style.get("language", "en"),
            series_name=episode.series.name if episode.series else "",
            series_description=episode.series.description if episode.series else "",
        )
    except AIError:
        raise HTTPException(status_code=502, detail="ERR_SCRIPT_GENERATION_FAILED")

    episode.brief = payload.brief
    episode.target_duration_sec = payload.target_duration_sec
    episode.script = script
    db.commit()
    return ScriptOut(script=script)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_script_generation.py tests/saas/test_episodes_routes.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add saas/ai/script_generation.py saas/schemas.py saas/routers/episodes.py tests/saas/test_script_generation.py
git commit -m "feat(ai): generate narration script to target duration via Claude"
```

---

### Task 4: Script analysis module + endpoint

**Files:**
- Create: `saas/ai/script_analysis.py`
- Modify: `saas/schemas.py`
- Modify: `saas/routers/episodes.py`
- Test: `tests/saas/test_script_analysis.py`

**Interfaces:**
- Consumes: `generate_json`, `AIError` from Task 2.
- Produces: `analyze_script(script: str, language: str, asset_catalog: list[dict]) -> list[dict]` — catalog items are `{"id", "kind", "name", "description"}`; returns scene dicts `{"narration_text": str, "asset_id": int | None, "asset_brief": str | None}` where an unknown/absent `asset_id` becomes `None` and `asset_brief` is then always a non-empty string.
- Produces: schema `AnalyzeScriptIn(script: str)`; endpoint `POST /episodes/{id}/analyze-script` → 200 `EpisodeOut`; replaces the episode's scenes; matched assets copy the SeriesAsset `object_key` onto `scene.asset_object_key`; 409 `ERR_EPISODE_NOT_DRAFT` unless `episode.status == "draft"`; 502 `ERR_SCRIPT_ANALYSIS_FAILED` on `AIError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_script_analysis.py`:

```python
import pytest
from fastapi.testclient import TestClient

import saas.ai.script_analysis as sa
import saas.routers.episodes as episodes_router
from saas.ai.client import AIError
from saas.db import get_db
from saas.main import app


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="owner@example.com"):
    response = client.post("/auth/signup", json={"email": email, "password": "pw12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


CATALOG = [
    {"id": 7, "kind": "character", "name": "hero", "description": "stick figure man"},
]


def test_analyze_script_passes_catalog_and_normalizes(monkeypatch):
    captured = {}

    def fake_generate_json(system, user_message, max_tokens=8192):
        captured["system"] = system
        return {
            "scenes": [
                {"narration_text": "Scene one.", "asset_id": 7, "asset_brief": None},
                {"narration_text": "Scene two.", "asset_id": 999, "asset_brief": None},
                {"narration_text": "Scene three.", "asset_id": None,
                 "asset_brief": "Ruined city street at dawn"},
            ]
        }

    monkeypatch.setattr(sa, "generate_json", fake_generate_json)
    scenes = sa.analyze_script("script text", "en", CATALOG)

    assert scenes[0] == {"narration_text": "Scene one.", "asset_id": 7, "asset_brief": None}
    # Unknown asset id 999 → treated as missing, with a non-empty brief.
    assert scenes[1]["asset_id"] is None
    assert scenes[1]["asset_brief"]
    assert scenes[2]["asset_brief"] == "Ruined city street at dawn"
    assert "hero" in captured["system"]


def test_analyze_script_rejects_empty_scenes(monkeypatch):
    monkeypatch.setattr(sa, "generate_json", lambda *a, **k: {"scenes": []})
    with pytest.raises(AIError):
        sa.analyze_script("s", "en", [])


def _episode_with_series(client, headers):
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    ep_id = client.post(
        "/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers
    ).json()["id"]
    return sid, ep_id


def test_endpoint_replaces_scenes_and_copies_matched_object_key(client, monkeypatch):
    headers = _auth(client)
    sid, ep_id = _episode_with_series(client, headers)

    # Insert a series asset with a known object_key directly through the DB layer
    # used by the app: upload route needs S3, so patch storage instead.
    monkeypatch.setattr(
        "saas.routers.series.save_series_asset", lambda *a, **k: "series/1/assets/1.png"
    )
    asset = client.post(
        f"/series/{sid}/assets",
        files={"file": ("hero.png", b"png-bytes", "image/png")},
        data={"kind": "character", "name": "hero", "description": "stick figure"},
        headers=headers,
    ).json()

    def fake_analyze(script, language, asset_catalog):
        assert asset_catalog[0]["name"] == "hero"
        return [
            {"narration_text": "One.", "asset_id": asset["id"], "asset_brief": None},
            {"narration_text": "Two.", "asset_id": None, "asset_brief": "A dark forest"},
        ]

    monkeypatch.setattr(episodes_router, "analyze_script", fake_analyze)

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "full script"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["script"] == "full script"
    assert len(body["scenes"]) == 2
    assert body["scenes"][0]["asset_object_key"] == "series/1/assets/1.png"
    assert body["scenes"][1]["asset_object_key"] is None
    assert body["scenes"][1]["asset_brief"] == "A dark forest"


def test_endpoint_conflicts_when_not_draft(client, monkeypatch):
    headers = _auth(client)
    _, ep_id = _episode_with_series(client, headers)
    # Force status past draft via the analyze path being blocked: mark built through DB.
    from saas.models import Episode
    db = client.app.dependency_overrides[get_db]().__next__()
    db.query(Episode).filter_by(id=ep_id).update({"status": "built"})
    db.commit()

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ERR_EPISODE_NOT_DRAFT"


def test_endpoint_maps_aierror_to_502(client, monkeypatch):
    def boom(script, language, asset_catalog):
        raise AIError("x")

    monkeypatch.setattr(episodes_router, "analyze_script", boom)
    headers = _auth(client)
    _, ep_id = _episode_with_series(client, headers)

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "ERR_SCRIPT_ANALYSIS_FAILED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_script_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.ai.script_analysis'`

- [ ] **Step 3: Write the module**

Create `saas/ai/script_analysis.py`:

```python
"""Split a narration script into scenes and match each to a series asset."""
from __future__ import annotations

import json

from .client import AIError, generate_json

LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def analyze_script(script: str, language: str, asset_catalog: list[dict]) -> list[dict]:
    language_name = LANGUAGE_NAMES.get(language, language)
    catalog_json = json.dumps(asset_catalog, ensure_ascii=False, indent=1)
    system = (
        "You split a narrated YouTube video script into visual scenes. "
        "Each scene is 1-4 sentences of narration shown over ONE still image. "
        f"The narration language is {language_name}.\n"
        f"Available images (the series asset catalog):\n{catalog_json}\n\n"
        "For each scene pick the best-matching asset id from the catalog, or null "
        "if none fits. When asset_id is null, write asset_brief: a detailed, "
        "self-contained ENGLISH image-generation prompt for the missing image "
        "(subject, setting, mood, composition). Keep the narration text verbatim — "
        "do not rewrite it, only split it.\n"
        'Reply with ONLY JSON: {"scenes": [{"narration_text": str, '
        '"asset_id": int | null, "asset_brief": str | null}]}'
    )
    result = generate_json(system, f"Script:\n{script}", max_tokens=16384)

    raw_scenes = result.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise AIError("Model reply missing non-empty 'scenes' list")

    valid_ids = {a["id"] for a in asset_catalog}
    scenes: list[dict] = []
    for raw in raw_scenes:
        narration = raw.get("narration_text")
        if not isinstance(narration, str) or not narration.strip():
            raise AIError("Scene missing narration_text")
        asset_id = raw.get("asset_id")
        brief = raw.get("asset_brief")
        if asset_id not in valid_ids:
            asset_id = None
        if asset_id is None and (not isinstance(brief, str) or not brief.strip()):
            brief = f"Illustration for: {narration.strip()[:200]}"
        scenes.append(
            {
                "narration_text": narration.strip(),
                "asset_id": asset_id,
                "asset_brief": brief.strip() if (asset_id is None and brief) else None,
            }
        )
    return scenes
```

- [ ] **Step 4: Add schema and endpoint**

In `saas/schemas.py`, after `ScriptOut`, add:

```python
class AnalyzeScriptIn(BaseModel):
    script: str
```

In `saas/routers/episodes.py`:

Add import:

```python
from ..ai.script_analysis import analyze_script
```

Extend the schemas import with `AnalyzeScriptIn`. Extend the models import with `SeriesAsset` if not present.

Add the endpoint after `generate_episode_script`:

```python
@router.post("/{episode_id}/analyze-script", response_model=EpisodeOut)
def analyze_episode_script(
    episode_id: int,
    payload: AnalyzeScriptIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if episode.status != "draft":
        raise HTTPException(status_code=409, detail="ERR_EPISODE_NOT_DRAFT")

    series = episode.series
    style = series.style if series else {}
    assets = series.assets if series else []
    catalog = [
        {"id": a.id, "kind": a.kind, "name": a.name, "description": a.description}
        for a in assets
    ]
    try:
        analyzed = analyze_script(payload.script, style.get("language", "en"), catalog)
    except AIError:
        raise HTTPException(status_code=502, detail="ERR_SCRIPT_ANALYSIS_FAILED")

    assets_by_id = {a.id: a for a in assets}
    episode.script = payload.script
    episode.scenes.clear()
    for index, item in enumerate(analyzed):
        matched = assets_by_id.get(item["asset_id"]) if item["asset_id"] else None
        episode.scenes.append(
            Scene(
                order_index=index,
                narration_text=item["narration_text"],
                asset_object_key=matched.object_key if matched else None,
                asset_brief=item["asset_brief"],
            )
        )
    db.commit()
    db.refresh(episode)
    return episode
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_script_analysis.py tests/saas/test_episodes_routes.py tests/saas/test_series_routes.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add saas/ai/script_analysis.py saas/schemas.py saas/routers/episodes.py tests/saas/test_script_analysis.py
git commit -m "feat(ai): split script into scenes with asset matching and missing-asset briefs"
```

---

### Task 5: Image provider + generate-asset endpoint

**Files:**
- Create: `saas/ai/image_provider.py`
- Modify: `saas/routers/episodes.py`
- Test: `tests/saas/test_image_provider.py`

**Interfaces:**
- Consumes: `save_series_asset(series_id, asset_id, filename, content) -> key` from `saas/storage.py`; `SeriesAsset` model with `source` from Task 1.
- Produces: `ImageError(RuntimeError)`; `class GptImageProvider` with `generate(prompt: str) -> bytes` (PNG bytes); `get_image_provider() -> GptImageProvider` reading env `IMAGE_PROVIDER` (default `gpt-image`), `OPENAI_API_KEY`, `IMAGE_MODEL` (default `gpt-image-1`), `IMAGE_SIZE` (default `1536x1024`).
- Produces: endpoint `POST /episodes/{id}/scenes/{scene_id}/generate-asset` → 200 `SceneOut`; creates a `SeriesAsset(source="generated")` and sets `scene.asset_object_key`; 400 `ERR_NO_SERIES` if the episode has no series; 400 `ERR_NO_ASSET_BRIEF` if the scene has no brief; 502 `ERR_IMAGE_GENERATION_FAILED` on `ImageError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_image_provider.py`:

```python
import base64

import pytest
from fastapi.testclient import TestClient

import saas.ai.image_provider as ip
import saas.routers.episodes as episodes_router
from saas.ai.image_provider import GptImageProvider, ImageError, get_image_provider
from saas.db import get_db
from saas.main import app


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="owner@example.com"):
    response = client.post("/auth/signup", json={"email": email, "password": "pw12345"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class FakeHttpResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_gpt_image_provider_decodes_b64(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        b64 = base64.b64encode(b"png-bytes").decode()
        return FakeHttpResponse(200, {"data": [{"b64_json": b64}]})

    monkeypatch.setattr(ip.requests, "post", fake_post)
    assert GptImageProvider().generate("a hero") == b"png-bytes"
    assert captured["json"]["model"] == "gpt-image-1"
    assert captured["json"]["prompt"] == "a hero"


def test_gpt_image_provider_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        ip.requests, "post", lambda *a, **k: FakeHttpResponse(400, {"error": "bad"})
    )
    with pytest.raises(ImageError):
        GptImageProvider().generate("x")


def test_get_image_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageError):
        get_image_provider()


def _episode_with_brief_scene(client, headers, monkeypatch):
    sid = client.post(
        "/series",
        json={"name": "S", "style": {"image_style_bible": "black stick figures, white bg"}},
        headers=headers,
    ).json()["id"]
    ep_id = client.post(
        "/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers
    ).json()["id"]
    monkeypatch.setattr(episodes_router, "analyze_script", lambda s, l, c: [
        {"narration_text": "One.", "asset_id": None, "asset_brief": "A dark forest"},
    ])
    ep = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers
    ).json()
    return sid, ep_id, ep["scenes"][0]["id"]


def test_generate_asset_endpoint(client, monkeypatch):
    headers = _auth(client)
    sid, ep_id, scene_id = _episode_with_brief_scene(client, headers, monkeypatch)

    captured = {}

    class FakeProvider:
        def generate(self, prompt):
            captured["prompt"] = prompt
            return b"png-bytes"

    monkeypatch.setattr(episodes_router, "get_image_provider", lambda: FakeProvider())
    monkeypatch.setattr(
        episodes_router, "save_series_asset",
        lambda series_id, asset_id, filename, content: f"series/{series_id}/assets/{asset_id}.png",
    )

    resp = client.post(
        f"/episodes/{ep_id}/scenes/{scene_id}/generate-asset", headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["asset_object_key"].startswith(f"series/{sid}/assets/")
    # Style bible must be appended to the prompt.
    assert "A dark forest" in captured["prompt"]
    assert "black stick figures" in captured["prompt"]

    assets = client.get(f"/series/{sid}/assets", headers=headers).json()
    assert assets[-1]["source"] == "generated"


def test_generate_asset_requires_brief(client, monkeypatch):
    headers = _auth(client)
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    ep = client.post(
        "/episodes",
        json={"title": "EP1", "series_id": sid, "scenes": [{"narration_text": "hi"}]},
        headers=headers,
    ).json()

    resp = client.post(
        f"/episodes/{ep['id']}/scenes/{ep['scenes'][0]['id']}/generate-asset", headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "ERR_NO_ASSET_BRIEF"


def test_generate_asset_requires_series(client, monkeypatch):
    headers = _auth(client)
    ep = client.post(
        "/episodes", json={"title": "EP1", "scenes": [{"narration_text": "hi"}]}, headers=headers
    ).json()

    resp = client.post(
        f"/episodes/{ep['id']}/scenes/{ep['scenes'][0]['id']}/generate-asset", headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "ERR_NO_SERIES"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_image_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.ai.image_provider'`

- [ ] **Step 3: Write the provider**

Create `saas/ai/image_provider.py`:

```python
"""Image generation behind a provider interface. Phase 1: OpenAI gpt-image only."""
from __future__ import annotations

import base64
import os

import requests

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


class ImageError(RuntimeError):
    pass


class GptImageProvider:
    def generate(self, prompt: str) -> bytes:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ImageError("OPENAI_API_KEY not set")
        response = requests.post(
            OPENAI_IMAGES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": os.environ.get("IMAGE_MODEL", "gpt-image-1"),
                "prompt": prompt,
                "size": os.environ.get("IMAGE_SIZE", "1536x1024"),
            },
            timeout=300,
        )
        if response.status_code != 200:
            raise ImageError(f"Image API failed ({response.status_code}): {response.text[:500]}")
        data = response.json().get("data") or []
        if not data or "b64_json" not in data[0]:
            raise ImageError("Image API returned no image data")
        return base64.b64decode(data[0]["b64_json"])


def get_image_provider() -> GptImageProvider:
    name = os.environ.get("IMAGE_PROVIDER", "gpt-image")
    if name != "gpt-image":
        raise ImageError(f"Unknown IMAGE_PROVIDER: {name}")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ImageError("OPENAI_API_KEY not set")
    return GptImageProvider()
```

- [ ] **Step 4: Add the endpoint**

In `saas/routers/episodes.py`:

Add imports:

```python
from ..ai.image_provider import ImageError, get_image_provider
from ..models import SeriesAsset
from ..storage import save_series_asset
```

(Merge into the existing import lines — `SeriesAsset` joins the models import, `save_series_asset` joins the storage import.)

Add the endpoint after `upload_scene_asset`:

```python
@router.post("/{episode_id}/scenes/{scene_id}/generate-asset", response_model=SceneOut)
def generate_scene_asset(
    episode_id: int,
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Scene:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    if episode.series is None:
        raise HTTPException(status_code=400, detail="ERR_NO_SERIES")
    if not scene.asset_brief:
        raise HTTPException(status_code=400, detail="ERR_NO_ASSET_BRIEF")

    style_bible = episode.series.style.get("image_style_bible", "")
    prompt = scene.asset_brief if not style_bible else f"{scene.asset_brief}\n\nStyle: {style_bible}"
    try:
        content = get_image_provider().generate(prompt)
    except ImageError:
        raise HTTPException(status_code=502, detail="ERR_IMAGE_GENERATION_FAILED")

    asset = SeriesAsset(
        series_id=episode.series.id,
        kind="other",
        name=f"ep{episode.id}-scene{scene.order_index + 1}",
        description=scene.asset_brief,
        source="generated",
    )
    db.add(asset)
    db.flush()  # allocate asset.id for the object key
    asset.object_key = save_series_asset(episode.series.id, asset.id, "generated.png", content)
    scene.asset_object_key = asset.object_key
    db.commit()
    return scene
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_image_provider.py tests/saas/test_episodes_routes.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add saas/ai/image_provider.py saas/routers/episodes.py tests/saas/test_image_provider.py
git commit -m "feat(ai): generate missing scene images via gpt-image provider"
```

---

### Task 6: TTS provider interface, wired into the build task

**Files:**
- Create: `saas/tts_providers.py`
- Modify: `saas/tasks.py:61-71` (the TTS loop in `run_build`)
- Test: `tests/saas/test_tts_providers.py`

**Interfaces:**
- Consumes: `agent_video.tts.synthesize_scene(text, out_path, api_key, voice_id)` (existing engine function, unchanged).
- Produces: `ElevenLabsTTS.synthesize(text: str, out_path: str, voice: str, language: str) -> None`; `AzureTTS.synthesize(...)` same signature; `get_tts_provider(name: str | None = None)` — `name` falls back to env `TTS_PROVIDER`, default `elevenlabs`; raises `ValueError` for unknown names.
- The build task reads `voice_id`, `tts_provider`, `language` from the episode's series `style` (empty dict when no series), falling back to env `ELEVENLABS_VOICE_ID` for the voice.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_tts_providers.py`:

```python
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

    def fake_synthesize_scene(text, out_path, api_key, voice_id):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_tts_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.tts_providers'`

- [ ] **Step 3: Write the module**

Create `saas/tts_providers.py`:

```python
"""TTS behind a provider interface: ElevenLabs (wraps the engine) and Azure Speech."""
from __future__ import annotations

import os
from xml.sax.saxutils import escape

import requests

from agent_video.tts import TTSError, synthesize_scene

AZURE_TTS_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


class ElevenLabsTTS:
    def synthesize(self, text: str, out_path: str, voice: str, language: str) -> None:
        synthesize_scene(
            text,
            out_path,
            os.environ.get("ELEVENLABS_API_KEY", ""),
            voice or os.environ.get("ELEVENLABS_VOICE_ID", ""),
        )


class AzureTTS:
    def synthesize(self, text: str, out_path: str, voice: str, language: str) -> None:
        key = os.environ.get("AZURE_SPEECH_KEY", "")
        region = os.environ.get("AZURE_SPEECH_REGION", "")
        if not key or not region:
            raise TTSError("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set")
        lang_tag = {"vi": "vi-VN", "en": "en-US"}.get(language, "en-US")
        ssml = (
            f"<speak version='1.0' xml:lang='{lang_tag}'>"
            f"<voice name='{voice}'>{escape(text)}</voice></speak>"
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


def get_tts_provider(name: str | None = None):
    resolved = name or os.environ.get("TTS_PROVIDER", "elevenlabs")
    if resolved == "elevenlabs":
        return ElevenLabsTTS()
    if resolved == "azure":
        return AzureTTS()
    raise ValueError(f"Unknown TTS provider: {resolved}")
```

- [ ] **Step 4: Wire into the build task**

In `saas/tasks.py`, remove the import of `synthesize_scene` from the `agent_video.tts` import line (keep `get_audio_duration`) and add:

```python
from .tts_providers import get_tts_provider
```

In `run_build`, replace this block:

```python
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
            voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
            for scene in engine_episode.scenes:
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                synthesize_scene(scene.text, audio_path, api_key, voice_id)
```

with:

```python
            style = episode.series.style if episode.series else {}
            tts = get_tts_provider(style.get("tts_provider"))
            voice = style.get("voice_id", "")
            language = style.get("language", "en")
            for scene in engine_episode.scenes:
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                tts.synthesize(scene.text, audio_path, voice=voice, language=language)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_tts_providers.py tests/saas/test_tasks.py -v`
Expected: all PASS. If `test_tasks.py` monkeypatched `saas.tasks.synthesize_scene`, update those patches to target `saas.tts_providers.synthesize_scene` (module-level engine function) — behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add saas/tts_providers.py saas/tasks.py tests/saas/test_tts_providers.py tests/saas/test_tasks.py
git commit -m "feat(tts): provider interface (ElevenLabs, Azure) wired into build task"
```

---

### Task 7: Vietnamese TTS voice comparison script (owner checkpoint)

**Files:**
- Create: `scripts/compare_tts_vi.py`

**Interfaces:**
- Consumes: `ElevenLabsTTS`, `AzureTTS` from Task 6.
- Produces: mp3 files under `videos/tts_compare/` for the project owner to listen to. No unit test — this is a manual comparison tool that intentionally calls real APIs.

- [ ] **Step 1: Write the script**

Create `scripts/compare_tts_vi.py`:

```python
"""Synthesize the same Vietnamese paragraph with every configured TTS voice.

Usage (from D:\\Video\\agent_video, with .env loaded):
    py scripts/compare_tts_vi.py

Configure candidates via env:
    ELEVENLABS_API_KEY + ELEVENLABS_COMPARE_VOICES  (comma-separated voice IDs)
    AZURE_SPEECH_KEY + AZURE_SPEECH_REGION           (voices are preset below)

Output: videos/tts_compare/<provider>_<voice>.mp3 — listen and pick a voice
for the series before producing EP 1.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from saas.tts_providers import AzureTTS, ElevenLabsTTS  # noqa: E402

SAMPLE_VI = (
    "Điều gì sẽ xảy ra nếu một buổi sáng, cả thành phố thức dậy và nhận ra "
    "mạng internet đã biến mất hoàn toàn? Không tin nhắn, không bản đồ, "
    "không một dòng tin tức. Trong ba phút tới, hãy cùng khám phá kịch bản "
    "đáng sợ nhưng hoàn toàn có thể xảy ra này."
)

AZURE_VI_VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]

OUT_DIR = os.path.join("videos", "tts_compare")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    produced = []

    el_voices = [v.strip() for v in os.environ.get("ELEVENLABS_COMPARE_VOICES", "").split(",") if v.strip()]
    if os.environ.get("ELEVENLABS_API_KEY") and el_voices:
        for voice in el_voices:
            path = os.path.join(OUT_DIR, f"elevenlabs_{voice}.mp3")
            print(f"ElevenLabs {voice} -> {path}")
            ElevenLabsTTS().synthesize(SAMPLE_VI, path, voice=voice, language="vi")
            produced.append(path)
    else:
        print("Skipping ElevenLabs (set ELEVENLABS_API_KEY and ELEVENLABS_COMPARE_VOICES)")

    if os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"):
        for voice in AZURE_VI_VOICES:
            path = os.path.join(OUT_DIR, f"azure_{voice}.mp3")
            print(f"Azure {voice} -> {path}")
            AzureTTS().synthesize(SAMPLE_VI, path, voice=voice, language="vi")
            produced.append(path)
    else:
        print("Skipping Azure (set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)")

    print(f"\nDone. {len(produced)} file(s) in {OUT_DIR}. Listen and pick a voice.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (real API keys required)**

Run: `py scripts/compare_tts_vi.py`
Expected: mp3 files appear under `videos/tts_compare/` for every configured provider. If no keys are configured, the script prints skip messages and exits cleanly — that still counts as the step passing; the owner adds keys and reruns.

- [ ] **Step 3: Notify the owner (do not block)**

Tell the project owner: "TTS comparison files are in `videos/tts_compare/` — please listen and pick the voice for the zombie series (needed before EP 1, Task 10). English series can use any ElevenLabs voice." Continue to Task 8 without waiting.

- [ ] **Step 4: Commit**

```bash
git add scripts/compare_tts_vi.py
git commit -m "feat(tts): add Vietnamese voice comparison script"
```

---

### Task 8: Frontend — Series pages + sidebar link

**Files:**
- Modify: `frontend/src/app/dashboard/layout.tsx` (NAV array)
- Create: `frontend/src/app/dashboard/series/page.tsx`
- Create: `frontend/src/app/dashboard/series/[id]/page.tsx`
- Test: `frontend/src/__tests__/series.test.tsx`

**Interfaces:**
- Consumes: `GET/POST /series`, `GET /series/{id}`, `GET/POST /series/{id}/assets` (multipart), `GET /episodes?series_id=` — all existing.
- Produces: pages at `/dashboard/series` and `/dashboard/series/[id]`; the detail page links to `/dashboard/episodes/new?series={id}` (consumed by Task 9).

- [ ] **Step 1: Write the failing Jest test**

Create `frontend/src/__tests__/series.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SeriesPage from "@/app/dashboard/series/page";
import * as apiModule from "@/lib/api";

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...rest }: { href: string; children: React.ReactNode; [k: string]: unknown }) => <a href={href} {...rest}>{children}</a> }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedApi = jest.mocked(apiModule.api);

beforeEach(() => jest.clearAllMocks());

describe("SeriesPage", () => {
  it("lists series from the API", async () => {
    mockedApi.get.mockResolvedValueOnce([
      { id: 1, name: "Zombie apocalypse", description: "", style: {}, episode_count: 3 },
    ]);
    render(<SeriesPage />);
    expect(await screen.findByText("Zombie apocalypse")).toBeInTheDocument();
    expect(screen.getByText(/3 episodes/i)).toBeInTheDocument();
  });

  it("creates a series with language and style bible", async () => {
    mockedApi.get.mockResolvedValueOnce([]);
    mockedApi.post.mockResolvedValueOnce({ id: 9, name: "New S", description: "", style: {}, episode_count: 0 });
    mockedApi.get.mockResolvedValueOnce([{ id: 9, name: "New S", description: "", style: {}, episode_count: 0 }]);

    const user = userEvent.setup();
    render(<SeriesPage />);
    await user.click(await screen.findByRole("button", { name: /new series/i }));
    await user.type(screen.getByPlaceholderText(/series name/i), "New S");
    await user.type(screen.getByPlaceholderText(/style bible/i), "black stick figures");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/series", {
        name: "New S",
        description: "",
        style: { language: "en", image_style_bible: "black stick figures", voice_id: "" },
      });
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- series` (from `frontend/`)
Expected: FAIL — module `@/app/dashboard/series/page` not found

- [ ] **Step 3: Add the sidebar link**

In `frontend/src/app/dashboard/layout.tsx`, in the `NAV` array, insert BEFORE the Episodes entry:

```tsx
  {
    href: "/dashboard/series",
    label: "Series",
    icon: (
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="5" width="12" height="9" rx="2" stroke="currentColor" strokeWidth="1.5" fill="none" />
        <path d="M4 5V3.5A1.5 1.5 0 015.5 2h5A1.5 1.5 0 0112 3.5V5" stroke="currentColor" strokeWidth="1.5" fill="none" />
      </svg>
    ),
  },
```

Note: the Episodes entry matches `pathname === "/dashboard"` exactly, so adding `/dashboard/series` does not break its active state.

- [ ] **Step 4: Build the series list page**

Create `frontend/src/app/dashboard/series/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";

interface Series {
  id: number;
  name: string;
  description: string;
  style: Record<string, unknown>;
  episode_count: number;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

export default function SeriesPage() {
  const [series, setSeries] = useState<Series[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("en");
  const [styleBible, setStyleBible] = useState("");
  const [voiceId, setVoiceId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      setSeries(await api.get<Series[]>("/series"));
    } catch {
      setError("Failed to load series.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Series name is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api.post<Series>("/series", {
        name: name.trim(),
        description,
        style: { language, image_style_bible: styleBible, voice_id: voiceId.trim() },
      });
      setShowForm(false);
      setName("");
      setDescription("");
      setStyleBible("");
      setVoiceId("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create series.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold" style={{ color: "#EDEDEF" }}>Series</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
        >
          New series
        </button>
      </div>

      {showForm && (
        <div className="p-4 rounded-2xl mb-6 flex flex-col gap-3" style={panel}>
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder="Series name" value={name} onChange={(e) => setName(e.target.value)} />
          <textarea className="px-3 py-2 rounded-lg text-sm" style={input} rows={2}
            placeholder="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <select className="px-3 py-2 rounded-lg text-sm w-40" style={input}
            value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Language">
            <option value="en">English</option>
            <option value="vi">Tiếng Việt</option>
          </select>
          <textarea className="px-3 py-2 rounded-lg text-sm" style={input} rows={3}
            placeholder="Style bible — describe the visual style used for every generated image (e.g. 'black stick figures on white background, minimal, bold red accents')"
            value={styleBible} onChange={(e) => setStyleBible(e.target.value)} />
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder="TTS voice ID (e.g. ElevenLabs voice id — pick after the voice comparison)"
            value={voiceId} onChange={(e) => setVoiceId(e.target.value)} />
          <button
            onClick={handleCreate}
            disabled={saving}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: saving ? 0.6 : 1 }}
          >
            Create
          </button>
        </div>
      )}

      {error && <p className="text-sm mb-4" style={{ color: "#FCA5A5" }}>{error}</p>}

      <div className="flex flex-col gap-3">
        {series.map((s) => (
          <Link key={s.id} href={`/dashboard/series/${s.id}`}
            className="p-4 rounded-2xl flex items-center justify-between" style={panel}>
            <div>
              <p className="text-sm font-semibold" style={{ color: "#EDEDEF" }}>{s.name}</p>
              {s.description && <p className="text-xs mt-1" style={{ color: "#8A8F98" }}>{s.description}</p>}
            </div>
            <span className="text-xs" style={{ color: "#8A8F98" }}>{s.episode_count} episodes</span>
          </Link>
        ))}
        {series.length === 0 && !showForm && (
          <p className="text-sm" style={{ color: "#8A8F98" }}>
            No series yet. A series holds shared character images, style, and voice for all its episodes.
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Build the series detail page**

Create `frontend/src/app/dashboard/series/[id]/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

interface Series {
  id: number;
  name: string;
  description: string;
  style: { language?: string; image_style_bible?: string; voice_id?: string };
  episode_count: number;
}

interface Asset {
  id: number;
  kind: string;
  name: string;
  description: string;
  object_key: string | null;
  source: string;
}

interface EpisodeListItem {
  id: number;
  title: string;
  status: string;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

export default function SeriesDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [series, setSeries] = useState<Series | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeListItem[]>([]);
  const [error, setError] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetKind, setAssetKind] = useState("character");
  const [assetDescription, setAssetDescription] = useState("");
  const [uploading, setUploading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, a, eps] = await Promise.all([
        api.get<Series>(`/series/${id}`),
        api.get<Asset[]>(`/series/${id}/assets`),
        api.get<EpisodeListItem[]>(`/episodes?series_id=${id}`),
      ]);
      setSeries(s);
      setAssets(a);
      setEpisodes(eps);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? "Series not found." : "Failed to load series.");
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleUpload(file: File) {
    if (!assetName.trim()) {
      setError("Asset name is required (the AI matches scenes to assets by name + description).");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const token = localStorage.getItem("access_token");
      const form = new FormData();
      form.append("file", file);
      form.append("kind", assetKind);
      form.append("name", assetName.trim());
      form.append("description", assetDescription);
      const res = await fetch(`/api/series/${id}/assets`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) throw new ApiError(res.status, "Upload failed");
      setAssetName("");
      setAssetDescription("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Asset upload failed.");
    } finally {
      setUploading(false);
    }
  }

  if (error && !series) return <div className="p-8"><p style={{ color: "#FCA5A5" }}>{error}</p></div>;
  if (!series) return <div className="p-8"><p style={{ color: "#8A8F98" }}>Loading…</p></div>;

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <Link href="/dashboard/series" className="text-sm mb-6 block w-fit" style={{ color: "#8A8F98" }}>
        ← All series
      </Link>
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "#EDEDEF" }}>{series.name}</h1>
          {series.description && <p className="text-sm mt-1" style={{ color: "#8A8F98" }}>{series.description}</p>}
          <p className="text-xs mt-2" style={{ color: "#4A4F5A" }}>
            Language: {series.style.language ?? "en"}
            {series.style.image_style_bible ? ` · Style: ${series.style.image_style_bible}` : ""}
          </p>
        </div>
        <Link
          href={`/dashboard/episodes/new?series=${series.id}`}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white flex-shrink-0"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)" }}
        >
          New episode
        </Link>
      </div>

      <section className="mb-8">
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#EDEDEF" }}>
          Shared assets ({assets.length})
        </h2>
        <div className="p-4 rounded-2xl mb-4 flex flex-col gap-3" style={panel}>
          <div className="flex gap-3">
            <input className="px-3 py-2 rounded-lg text-sm flex-1" style={input}
              placeholder="Asset name (e.g. main_character)" value={assetName}
              onChange={(e) => setAssetName(e.target.value)} />
            <select className="px-3 py-2 rounded-lg text-sm" style={input} value={assetKind}
              onChange={(e) => setAssetKind(e.target.value)} aria-label="Kind">
              <option value="character">character</option>
              <option value="location">location</option>
              <option value="object">object</option>
              <option value="other">other</option>
            </select>
          </div>
          <input className="px-3 py-2 rounded-lg text-sm" style={input}
            placeholder="Description — what is in this image (the AI matches scenes by this)"
            value={assetDescription} onChange={(e) => setAssetDescription(e.target.value)} />
          <label className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit cursor-pointer"
            style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: uploading ? 0.6 : 1 }}>
            {uploading ? "Uploading…" : "Upload image"}
            <input type="file" accept="image/*" className="hidden" disabled={uploading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
                e.target.value = "";
              }} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {assets.map((a) => (
            <div key={a.id} className="p-3 rounded-xl" style={panel}>
              <p className="text-sm font-medium" style={{ color: "#EDEDEF" }}>
                {a.name}
                <span className="text-xs ml-2 px-1.5 py-0.5 rounded" style={{
                  background: a.source === "generated" ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.06)",
                  color: a.source === "generated" ? "#818CF8" : "#8A8F98",
                }}>
                  {a.source === "generated" ? "AI" : a.kind}
                </span>
              </p>
              {a.description && <p className="text-xs mt-1" style={{ color: "#8A8F98" }}>{a.description}</p>}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold mb-3" style={{ color: "#EDEDEF" }}>Episodes</h2>
        <div className="flex flex-col gap-2">
          {episodes.map((ep) => (
            <Link key={ep.id} href={`/dashboard/episodes/${ep.id}`}
              className="p-3 rounded-xl flex items-center justify-between" style={panel}>
              <span className="text-sm" style={{ color: "#EDEDEF" }}>{ep.title}</span>
              <span className="text-xs" style={{ color: "#8A8F98" }}>{ep.status}</span>
            </Link>
          ))}
          {episodes.length === 0 && <p className="text-sm" style={{ color: "#8A8F98" }}>No episodes yet.</p>}
        </div>
      </section>

      {error && <p className="text-sm mt-4" style={{ color: "#FCA5A5" }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npm test -- series` (from `frontend/`), then the full suite `npm test`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/dashboard/layout.tsx frontend/src/app/dashboard/series frontend/src/__tests__/series.test.tsx
git commit -m "feat(frontend): series pages with shared assets and sidebar link"
```

---

### Task 9: Frontend — script-first episode flow

**Files:**
- Create: `frontend/src/components/episode/ScriptPanel.tsx`
- Modify: `frontend/src/app/dashboard/episodes/new/page.tsx` (add series/brief/duration fields)
- Modify: `frontend/src/app/dashboard/episodes/[id]/page.tsx` (render ScriptPanel; generate-image button on scenes)
- Test: `frontend/src/__tests__/script-panel.test.tsx`

**Interfaces:**
- Consumes: `POST /episodes/{id}/generate-script` (Task 3), `POST /episodes/{id}/analyze-script` (Task 4), `POST /episodes/{id}/scenes/{sid}/generate-asset` (Task 5); `EpisodeOut.script/brief/target_duration_sec` and `SceneOut.asset_brief` (Task 1); `GET /series` (existing).
- Produces: `<ScriptPanel episodeId={number} initialBrief={string} initialDurationSec={number | null} initialScript={string} disabled={boolean} onEpisodeUpdated={() => void} />`.

- [ ] **Step 1: Write the failing Jest test**

Create `frontend/src/__tests__/script-panel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScriptPanel from "@/components/episode/ScriptPanel";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

const mockedApi = jest.mocked(apiModule.api);

beforeEach(() => jest.clearAllMocks());

function setup(overrides: Partial<Parameters<typeof ScriptPanel>[0]> = {}) {
  const onEpisodeUpdated = jest.fn();
  render(
    <ScriptPanel
      episodeId={5}
      initialBrief=""
      initialDurationSec={null}
      initialScript=""
      disabled={false}
      onEpisodeUpdated={onEpisodeUpdated}
      {...overrides}
    />
  );
  return { onEpisodeUpdated };
}

describe("ScriptPanel", () => {
  it("generates a script from brief + duration", async () => {
    mockedApi.post.mockResolvedValueOnce({ script: "Generated narration." });
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByPlaceholderText(/episode idea/i), "zombie outbreak");
    await user.clear(screen.getByLabelText(/minutes/i));
    await user.type(screen.getByLabelText(/minutes/i), "8");
    await user.click(screen.getByRole("button", { name: /generate script/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes/5/generate-script", {
        brief: "zombie outbreak",
        target_duration_sec: 480,
      });
    });
    expect(await screen.findByDisplayValue("Generated narration.")).toBeInTheDocument();
  });

  it("analyzes the edited script into scenes", async () => {
    mockedApi.post.mockResolvedValueOnce({ id: 5, scenes: [] });
    const user = userEvent.setup();
    const { onEpisodeUpdated } = setup({ initialScript: "Existing script." });

    await user.click(screen.getByRole("button", { name: /split into scenes/i }));

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith("/episodes/5/analyze-script", {
        script: "Existing script.",
      });
      expect(onEpisodeUpdated).toHaveBeenCalled();
    });
  });

  it("shows a friendly error on ERR_SCRIPT_GENERATION_FAILED", async () => {
    mockedApi.post.mockRejectedValueOnce(new ApiError(502, "ERR_SCRIPT_GENERATION_FAILED"));
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByPlaceholderText(/episode idea/i), "x");
    await user.click(screen.getByRole("button", { name: /generate script/i }));

    expect(await screen.findByText(/script generation failed/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- script-panel` (from `frontend/`)
Expected: FAIL — module `@/components/episode/ScriptPanel` not found

- [ ] **Step 3: Build ScriptPanel**

Create `frontend/src/components/episode/ScriptPanel.tsx`:

```tsx
"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

interface Props {
  episodeId: number;
  initialBrief: string;
  initialDurationSec: number | null;
  initialScript: string;
  disabled: boolean;
  onEpisodeUpdated: () => void;
}

const panel = { background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" };
const input = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#EDEDEF",
};

const ERROR_MESSAGES: Record<string, string> = {
  ERR_SCRIPT_GENERATION_FAILED: "Script generation failed — please try again.",
  ERR_SCRIPT_ANALYSIS_FAILED: "Scene analysis failed — please try again.",
  ERR_EPISODE_NOT_DRAFT: "Scenes can only be regenerated while the episode is a draft.",
};

export default function ScriptPanel({
  episodeId,
  initialBrief,
  initialDurationSec,
  initialScript,
  disabled,
  onEpisodeUpdated,
}: Props) {
  const [brief, setBrief] = useState(initialBrief);
  const [minutes, setMinutes] = useState(initialDurationSec ? Math.round(initialDurationSec / 60) : 8);
  const [script, setScript] = useState(initialScript);
  const [generating, setGenerating] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  function friendly(err: unknown, fallback: string) {
    if (err instanceof ApiError) return ERROR_MESSAGES[err.detail] ?? err.detail;
    return fallback;
  }

  async function handleGenerate() {
    if (!brief.trim()) {
      setError("Enter an episode idea first.");
      return;
    }
    setGenerating(true);
    setError("");
    try {
      const { script: generated } = await api.post<{ script: string }>(
        `/episodes/${episodeId}/generate-script`,
        { brief: brief.trim(), target_duration_sec: minutes * 60 }
      );
      setScript(generated);
      onEpisodeUpdated();
    } catch (err) {
      setError(friendly(err, "Script generation failed."));
    } finally {
      setGenerating(false);
    }
  }

  async function handleAnalyze() {
    if (!script.trim()) {
      setError("Write or generate a script first.");
      return;
    }
    setAnalyzing(true);
    setError("");
    try {
      await api.post(`/episodes/${episodeId}/analyze-script`, { script: script.trim() });
      onEpisodeUpdated();
    } catch (err) {
      setError(friendly(err, "Scene analysis failed."));
    } finally {
      setAnalyzing(false);
    }
  }

  const busy = disabled || generating || analyzing;

  return (
    <section className="mb-8 p-4 rounded-2xl flex flex-col gap-3" style={panel}>
      <h2 className="text-sm font-semibold" style={{ color: "#EDEDEF" }}>Script</h2>

      <textarea
        className="px-3 py-2 rounded-lg text-sm"
        style={input}
        rows={2}
        placeholder="Episode idea / brief — a rough idea or a partial script"
        value={brief}
        onChange={(e) => setBrief(e.target.value)}
        disabled={busy}
      />
      <div className="flex items-center gap-3">
        <label className="text-xs" style={{ color: "#8A8F98" }} htmlFor="duration-minutes">
          Target minutes
        </label>
        <input
          id="duration-minutes"
          aria-label="Target minutes"
          type="number"
          min={1}
          max={60}
          className="px-3 py-2 rounded-lg text-sm w-20"
          style={input}
          value={minutes}
          onChange={(e) => setMinutes(Number(e.target.value) || 1)}
          disabled={busy}
        />
        <button
          onClick={handleGenerate}
          disabled={busy}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #6366F1, #4F46E5)", opacity: busy ? 0.6 : 1 }}
        >
          {generating ? "Generating…" : "Generate script"}
        </button>
      </div>

      <textarea
        className="px-3 py-2 rounded-lg text-sm font-mono"
        style={input}
        rows={10}
        placeholder="The full narration script appears here — edit freely before splitting into scenes. You can also paste a finished script directly."
        value={script}
        onChange={(e) => setScript(e.target.value)}
        disabled={busy}
      />
      <button
        onClick={handleAnalyze}
        disabled={busy || !script.trim()}
        className="px-4 py-2 rounded-xl text-sm font-semibold text-white w-fit"
        style={{
          background: script.trim() ? "linear-gradient(135deg, #10B981, #059669)" : "rgba(16,185,129,0.25)",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {analyzing ? "Splitting…" : "Split into scenes"}
      </button>
      <p className="text-xs" style={{ color: "#4A4F5A" }}>
        Splitting replaces the current scene list and matches each scene to your series assets.
      </p>

      {error && <p className="text-sm" style={{ color: "#FCA5A5" }}>{error}</p>}
    </section>
  );
}
```

- [ ] **Step 4: Wire into the episode detail page**

In `frontend/src/app/dashboard/episodes/[id]/page.tsx`:

1. Add the import:

```tsx
import ScriptPanel from "@/components/episode/ScriptPanel";
```

2. Extend the local interfaces — `Scene` gains `asset_brief: string | null;`, `Episode` gains:

```tsx
  brief: string;
  script: string;
  target_duration_sec: number | null;
  series_id: number | null;
```

3. Add a generating state next to `uploadingScene`:

```tsx
  const [generatingScene, setGeneratingScene] = useState<number | null>(null);
```

4. Add the handler after `handleAssetUpload`:

```tsx
  async function handleGenerateAsset(scene: Scene) {
    setGeneratingScene(scene.id);
    setJobError("");
    try {
      await api.post(`/episodes/${id}/scenes/${scene.id}/generate-asset`, {});
      await fetchEpisode();
    } catch (err) {
      if (err instanceof ApiError && err.detail === "ERR_IMAGE_GENERATION_FAILED") {
        setJobError("Image generation failed — try again or upload manually.");
      } else {
        setJobError(err instanceof ApiError ? err.detail : "Image generation failed.");
      }
    } finally {
      setGeneratingScene(null);
    }
  }
```

5. Render the ScriptPanel between the Header and the Scenes section (only editable in draft):

```tsx
      {episode.status === "draft" && (
        <ScriptPanel
          episodeId={episode.id}
          initialBrief={episode.brief}
          initialDurationSec={episode.target_duration_sec}
          initialScript={episode.script}
          disabled={isBusy}
          onEpisodeUpdated={fetchEpisode}
        />
      )}
```

6. In the scene card (inside `episode.scenes.map`), under the narration `<p>`, show the missing-image brief and a generate button. Insert BEFORE the existing upload `<label>` (inside the same `flex items-center gap-3` div):

```tsx
                  {!scene.asset_object_key && scene.asset_brief && (
                    <button
                      onClick={() => handleGenerateAsset(scene)}
                      disabled={isBusy || generatingScene !== null}
                      className="flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg transition-all"
                      style={{
                        background: "rgba(99,102,241,0.12)",
                        border: "1px solid rgba(99,102,241,0.25)",
                        color: "#818CF8",
                        opacity: isBusy ? 0.5 : 1,
                      }}
                      title={scene.asset_brief}
                    >
                      {generatingScene === scene.id ? (
                        <div className="w-3 h-3 rounded-full border border-t-transparent animate-spin" style={{ borderColor: "#818CF8", borderTopColor: "transparent" }} />
                      ) : (
                        "✨"
                      )}
                      Generate image
                    </button>
                  )}
```

And directly under the narration `<p className="text-sm mb-3" ...>` add the brief display:

```tsx
                {!scene.asset_object_key && scene.asset_brief && (
                  <p className="text-xs mb-2 italic" style={{ color: "#8A8F98" }}>
                    Missing image: {scene.asset_brief}
                  </p>
                )}
```

- [ ] **Step 5: Add series/brief/duration to the new-episode page**

In `frontend/src/app/dashboard/episodes/new/page.tsx`:

1. Read the `?series=` query param and load the user's series list. Add imports (`useSearchParams` from `next/navigation`) and state near the other state hooks. Note: Next.js 14 requires a `<Suspense>` boundary around components using `useSearchParams` during `next build` — if the build errors, extract the page body into an inner component and wrap it: `export default function Page() { return <Suspense><NewEpisodeInner /></Suspense>; }`.

```tsx
  const searchParams = useSearchParams();
  const [seriesList, setSeriesList] = useState<{ id: number; name: string }[]>([]);
  const [seriesId, setSeriesId] = useState<number | null>(
    searchParams.get("series") ? Number(searchParams.get("series")) : null
  );

  useEffect(() => {
    api.get<{ id: number; name: string }[]>("/series").then(setSeriesList).catch(() => {});
  }, []);
```

2. Render a series select above the title input (values: "No series" + one option per series):

```tsx
      <select
        className="px-3 py-2 rounded-lg text-sm w-full mb-4"
        style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", color: "#EDEDEF" }}
        value={seriesId ?? ""}
        onChange={(e) => setSeriesId(e.target.value ? Number(e.target.value) : null)}
        aria-label="Series"
      >
        <option value="">No series (standalone)</option>
        {seriesList.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
```

3. Include `series_id: seriesId` in the existing `api.post("/episodes", {...})` payload. Scenes stay as-is — the manual scene flow still works; the AI flow adds scenes later via analyze-script (an episode created with zero scenes is now valid: delete/adjust any client-side validation that requires at least one scene with narration, keeping the rule "if any scene exists, it needs narration").

- [ ] **Step 6: Run tests to verify they pass**

Run: `npm test` (from `frontend/`)
Expected: all PASS — including the pre-existing `new-episode.test.tsx`; update its expectations if the zero-scene rule change affects them (the "posts to /episodes" test should now also expect `series_id: null`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/episode frontend/src/app/dashboard/episodes frontend/src/__tests__/script-panel.test.tsx frontend/src/__tests__/new-episode.test.tsx
git commit -m "feat(frontend): script-first episode flow with generate/analyze and image generation"
```

---

### Task 10: Produce EP 1 for real (end-to-end checkpoint — needs the project owner)

**Files:** none (manual verification against the running stack)

This is the Phase-1 exit checkpoint from the spec. It requires the project owner (voice choice, script approval, judging the output) and real API keys. An agentic worker prepares the environment and walks the owner through it; it cannot complete this task alone.

- [ ] **Step 1: Preflight**

- `.env` has: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, DB/S3/JWT vars (see `SETUP.md`), optionally `ANTHROPIC_MODEL`, `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION`.
- Task 1 Step 6 ALTERs applied to the dev DB.
- Owner has picked a voice from Task 7's `videos/tts_compare/` output (or decided EP 1 is English).
- Start the stack: `docker compose up -d` then backend + Celery + frontend per `SETUP.md`; log in as `demo@local.test`.

- [ ] **Step 2: Create the series with the owner**

In `/dashboard/series`: create the zombie series — name, description, language (owner's choice), style bible describing the stick-figure look, and the TTS voice ID chosen in Task 7. If a non-ElevenLabs provider won (`tts_provider: "azure"`), the create form has no field for it yet — POST /series via curl with the complete style object instead.

- [ ] **Step 3: Upload the shared assets**

Upload the images from `D:\Video\Seri 1\EP 1` as series assets with meaningful names + descriptions (characters, locations, objects, phone-UI screens). Good descriptions directly improve scene matching.

- [ ] **Step 4: Run the AI flow**

Create the episode from the series page → enter the brief (or paste the owner's script) + target minutes → Generate script → owner edits/approves → Split into scenes → review matches; for each missing image either Generate image (check style consistency against the style bible) or create it externally and upload.

- [ ] **Step 5: Build, review, publish**

Build episode → watch the output video with the owner (voice quality, caption timing, scene pacing, music) → if acceptable, connect YouTube and publish. Record any defects as a punch list in `docs/superpowers/plans/2026-07-10-ep1-punchlist.md` — pacing/effect/editor gaps feed Phase 2/3 design.

- [ ] **Step 6: Repeat for EP 2-3**

Same flow, reusing the series assets (this validates the "series consistency" positioning: character images persist, generated assets accumulate). Phase 1 is DONE when 3 episodes are complete; EP 2-3 may happen in later sessions — do not block this plan's completion review on them, but note their status.

---

## Env vars introduced by this plan

| Var | Used by | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Task 2 client | required for AI features |
| `ANTHROPIC_MODEL` | Task 2 client | `claude-sonnet-5` |
| `OPENAI_API_KEY` | Task 5 image provider | required for image gen |
| `IMAGE_PROVIDER` / `IMAGE_MODEL` / `IMAGE_SIZE` | Task 5 | `gpt-image` / `gpt-image-1` / `1536x1024` |
| `TTS_PROVIDER` | Task 6 factory | `elevenlabs` |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` | Task 6 AzureTTS, Task 7 | optional |
| `ELEVENLABS_COMPARE_VOICES` | Task 7 script | optional |

Add these to `SETUP.md`'s env table when touching it; do not create a separate env doc.
