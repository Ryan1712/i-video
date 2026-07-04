# Phase 1: Series + Script-Analysis Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Series (project) grouping with shared assets, an LLM endpoint that splits a pasted script into scenes and produces a missing-asset checklist, the frontend for both — then produce real Episode 1 of the zombie series with the app.

**Architecture:** New `series` / `series_assets` tables; `episodes.series_id` FK; `scenes.asset_brief` column. New FastAPI router `/series` following the existing episodes-router patterns (JWT auth, owner-scoped 404s, S3 object keys). New `saas/script_analysis.py` module calls Claude (`claude-opus-4-8`) with structured outputs to turn a raw script + the series asset catalog into scenes with matched/missing assets. Frontend adds Series pages and a paste-script flow. Render pipeline is unchanged (still the existing ffmpeg build task).

**Tech Stack:** FastAPI, SQLAlchemy 2 (Mapped/mapped_column), Pydantic, Celery (untouched), `anthropic` Python SDK, Next.js 14 App Router, Jest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-04-product-vision-v2-design.md` (Phase 1 section).
- Run backend tests with `py -m pytest tests/saas/<file> -v` from `D:\Video\agent_video`. Tests use the in-memory SQLite fixtures in `tests/saas/conftest.py` — never a real Postgres.
- There is no migration tool. New TABLES are created by `Base.metadata.create_all`; new COLUMNS on existing tables need the manual `ALTER TABLE` statements in Task 1 Step 6 (dev DB only).
- API error codes are stable strings (`ERR_...`) in `detail`; frontend owns translation.
- Ownership checks return 404 (not 403) for other users' resources, matching `_get_owned_episode_or_404`.
- Claude model ID is exactly `claude-opus-4-8`. Never a date-suffixed variant.
- Frontend calls go through the `/api` proxy (`lib/api.ts`); multipart uploads use raw `fetch("/api/...")` with the Bearer token, NOT `http://localhost:8000`.
- Commit messages follow the existing `feat(scope): ...` convention.

---

### Task 1: DB models + schemas (Series, SeriesAsset, episode/scene columns)

**Files:**
- Modify: `saas/models.py`
- Modify: `saas/schemas.py`
- Test: `tests/saas/test_series_models.py`

**Interfaces:**
- Produces: models `Series(id, user_id, name, description, style, created_at, assets, episodes)`, `SeriesAsset(id, series_id, kind, name, description, object_key, created_at)`; `Episode.series_id: int | None`; `Scene.asset_brief: str | None`.
- Produces: schemas `SeriesIn(name, description="", style={})`, `SeriesOut(id, name, description, style, episode_count)`, `SeriesAssetOut(id, kind, name, description, object_key)`; `SceneOut` gains `asset_brief: str | None = None`; `EpisodeIn` gains `series_id: int | None = None`; `EpisodeOut` gains `series_id: int | None = None`.

- [ ] **Step 1: Write the failing test**

Create `tests/saas/test_series_models.py`:

```python
from saas.models import Episode, Scene, Series, SeriesAsset, User


def _make_user(db_session, email="owner@example.com"):
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def test_series_with_assets_roundtrip(db_session):
    user = _make_user(db_session)
    series = Series(
        user_id=user.id,
        name="What if zombies",
        description="10-episode zombie apocalypse series",
        style={"voice_id": "abc", "caption_style": "bold"},
    )
    series.assets.append(
        SeriesAsset(kind="character", name="main_character",
                    description="Stick figure man, torn jacket", object_key="series/1/assets/1.png")
    )
    db_session.add(series)
    db_session.commit()

    loaded = db_session.query(Series).one()
    assert loaded.style["voice_id"] == "abc"
    assert loaded.assets[0].kind == "character"
    assert loaded.assets[0].series_id == loaded.id


def test_episode_links_to_series_and_scene_has_asset_brief(db_session):
    user = _make_user(db_session)
    series = Series(user_id=user.id, name="S1")
    db_session.add(series)
    db_session.commit()

    episode = Episode(user_id=user.id, title="EP1", series_id=series.id)
    episode.scenes.append(
        Scene(order_index=0, narration_text="intro", asset_brief="Bedroom at dawn, stick figure waking up")
    )
    db_session.add(episode)
    db_session.commit()

    loaded = db_session.query(Episode).one()
    assert loaded.series_id == series.id
    assert loaded.scenes[0].asset_brief.startswith("Bedroom")


def test_episode_series_id_is_optional(db_session):
    user = _make_user(db_session)
    episode = Episode(user_id=user.id, title="standalone")
    db_session.add(episode)
    db_session.commit()
    assert db_session.query(Episode).one().series_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_series_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Series'`

- [ ] **Step 3: Add the models**

In `saas/models.py`, after the `SiteSetting` class and before `Episode`, add:

```python
class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    assets: Mapped[list["SeriesAsset"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    episodes: Mapped[list["Episode"]] = relationship(back_populates="series")


class SeriesAsset(Base):
    __tablename__ = "series_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    series: Mapped["Series"] = relationship(back_populates="assets")
```

In `Episode`, add after `user_id`:

```python
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"), nullable=True)
```

and add to `Episode`'s relationships:

```python
    series: Mapped["Series | None"] = relationship(back_populates="episodes")
```

In `Scene`, add after `asset_object_key`:

```python
    asset_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Add the schemas**

In `saas/schemas.py`, add after `TokenResponse`:

```python
class SeriesIn(BaseModel):
    name: str
    description: str = ""
    style: dict = {}


class SeriesOut(BaseModel):
    id: int
    name: str
    description: str
    style: dict
    episode_count: int = 0

    class Config:
        from_attributes = True


class SeriesAssetOut(BaseModel):
    id: int
    kind: str
    name: str
    description: str
    object_key: str | None

    class Config:
        from_attributes = True
```

In `SceneOut`, add field `asset_brief: str | None = None`. In `EpisodeIn`, add field `series_id: int | None = None`. In `EpisodeOut`, add field `series_id: int | None = None`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_series_models.py tests/saas/test_models.py tests/saas/test_episodes_routes.py -v`
Expected: all PASS (existing episode tests must not break).

- [ ] **Step 6: Update the dev database (new columns need manual ALTER)**

Run (Postgres container must be up; `docker compose up -d` in repo root first if not):

```powershell
docker exec agent_video-postgres-1 psql -U whatif -d whatif -c "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS series_id INTEGER REFERENCES series(id); ALTER TABLE scenes ADD COLUMN IF NOT EXISTS asset_brief TEXT;"
```

Note: this will fail with `relation "series" does not exist` until the new tables are created. Create tables first:

```powershell
py -c "from dotenv import load_dotenv; load_dotenv(); import saas.models; from saas.db import Base, init_session_factory; Base.metadata.create_all(init_session_factory().kw['bind']); print('ok')"
```

then run the `ALTER TABLE` above. Expected final output: `ALTER TABLE`.

- [ ] **Step 7: Commit**

```powershell
git add saas/models.py saas/schemas.py tests/saas/test_series_models.py
git commit -m "feat(series): add Series and SeriesAsset models, episode series link, scene asset_brief"
```

---

### Task 2: Series router (CRUD + shared asset upload)

**Files:**
- Create: `saas/routers/series.py`
- Modify: `saas/storage.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_series_routes.py`

**Interfaces:**
- Consumes: Task 1 models/schemas; `saas.storage.upload_bytes`-based helpers; `get_current_user`, `get_db`.
- Produces: routes `POST /series` (201, SeriesOut), `GET /series` (list[SeriesOut] with `episode_count`), `GET /series/{series_id}` (SeriesOut), `GET /series/{series_id}/assets` (list[SeriesAssetOut]), `POST /series/{series_id}/assets` (201, SeriesAssetOut; multipart `file` + form fields `kind`, `name`, `description`), `GET /series/{series_id}/assets/{asset_id}/url` (AssetUrlOut). Storage helper `save_series_asset(series_id, asset_id, filename, content) -> str` with key `series/{series_id}/assets/{asset_id}{ext}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_series_routes.py`:

```python
import io

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

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


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def test_create_and_list_series(client):
    headers = _auth(client)
    created = client.post(
        "/series",
        json={"name": "Zombie apocalypse", "description": "d", "style": {"voice_id": "v1"}},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["style"] == {"voice_id": "v1"}

    listed = client.get("/series", headers=headers)
    assert [s["name"] for s in listed.json()] == ["Zombie apocalypse"]
    assert listed.json()[0]["episode_count"] == 0


def test_series_is_owner_scoped(client):
    headers_a = _auth(client, "a@example.com")
    headers_b = _auth(client, "b@example.com")
    sid = client.post("/series", json={"name": "A's"}, headers=headers_a).json()["id"]

    assert client.get(f"/series/{sid}", headers=headers_b).status_code == 404
    assert client.get("/series", headers=headers_b).json() == []


def test_episode_count_reflects_linked_episodes(client):
    headers = _auth(client)
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    client.post("/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers)

    listed = client.get("/series", headers=headers)
    assert listed.json()[0]["episode_count"] == 1


@mock_aws
def test_upload_series_asset(client, monkeypatch):
    _set_s3_env(monkeypatch)
    import boto3
    boto3.client("s3").create_bucket(Bucket="whatif-test-bucket")

    headers = _auth(client)
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]

    response = client.post(
        f"/series/{sid}/assets",
        files={"file": ("hero.png", io.BytesIO(b"png-bytes"), "image/png")},
        data={"kind": "character", "name": "main_character", "description": "Stick figure man"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["object_key"] == f"series/{sid}/assets/{body['id']}.png"

    assets = client.get(f"/series/{sid}/assets", headers=headers).json()
    assert assets[0]["name"] == "main_character"

    url = client.get(f"/series/{sid}/assets/{body['id']}/url", headers=headers)
    assert url.status_code == 200
    assert "series/" in url.json()["url"]
```

Note: `test_episode_count_reflects_linked_episodes` will only pass fully after Task 3 wires `series_id` through episode creation; if it fails on the episode step, mark it `@pytest.mark.xfail(reason="episode series_id lands in task 3")` and remove the marker in Task 3.

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_series_routes.py -v`
Expected: FAIL with 404s (`POST /series` route does not exist).

- [ ] **Step 3: Add the storage helper**

In `saas/storage.py`, add after `save_asset`:

```python
def save_series_asset(series_id: int, asset_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    key = f"series/{series_id}/assets/{asset_id}{ext}"
    upload_bytes(key, content)
    return key
```

- [ ] **Step 4: Write the router**

Create `saas/routers/series.py`:

```python
"""Series (project) CRUD and shared-asset routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Series, SeriesAsset, User
from ..schemas import AssetUrlOut, SeriesAssetOut, SeriesIn, SeriesOut
from ..storage import presigned_asset_url, save_series_asset

router = APIRouter(prefix="/series", tags=["series"])


def _get_owned_series_or_404(series_id: int, db: Session, current_user: User) -> Series:
    series = db.query(Series).filter_by(id=series_id, user_id=current_user.id).one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def _to_out(series: Series, db: Session) -> SeriesOut:
    count = db.query(Episode).filter_by(series_id=series.id).count()
    out = SeriesOut.model_validate(series)
    out.episode_count = count
    return out


@router.post("", response_model=SeriesOut, status_code=201)
def create_series(
    payload: SeriesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesOut:
    series = Series(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        style=payload.style,
    )
    db.add(series)
    db.commit()
    return _to_out(series, db)


@router.get("", response_model=list[SeriesOut])
def list_series(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[SeriesOut]:
    all_series = db.query(Series).filter_by(user_id=current_user.id).all()
    return [_to_out(s, db) for s in all_series]


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesOut:
    return _to_out(_get_owned_series_or_404(series_id, db, current_user), db)


@router.get("/{series_id}/assets", response_model=list[SeriesAssetOut])
def list_series_assets(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SeriesAsset]:
    return _get_owned_series_or_404(series_id, db, current_user).assets


@router.post("/{series_id}/assets", response_model=SeriesAssetOut, status_code=201)
async def upload_series_asset(
    series_id: int,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesAsset:
    series = _get_owned_series_or_404(series_id, db, current_user)
    asset = SeriesAsset(series_id=series.id, kind=kind, name=name, description=description)
    db.add(asset)
    db.flush()  # allocate asset.id for the object key

    content = await file.read()
    asset.object_key = save_series_asset(series.id, asset.id, file.filename, content)
    db.commit()
    return asset


@router.get("/{series_id}/assets/{asset_id}/url", response_model=AssetUrlOut)
def get_series_asset_url(
    series_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetUrlOut:
    series = _get_owned_series_or_404(series_id, db, current_user)
    asset = next((a for a in series.assets if a.id == asset_id), None)
    if asset is None or asset.object_key is None:
        raise HTTPException(status_code=404, detail="Series asset not found")
    return AssetUrlOut(url=presigned_asset_url(asset.object_key))
```

- [ ] **Step 5: Register the router**

In `saas/main.py`: add `series` to the `from .routers import (...)` list and `app.include_router(series.router)` next to the other `include_router` calls.

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_series_routes.py -v`
Expected: PASS (except the xfail-marked one if Task 3 not done).

- [ ] **Step 7: Commit**

```powershell
git add saas/routers/series.py saas/storage.py saas/main.py tests/saas/test_series_routes.py
git commit -m "feat(series): add series CRUD and shared-asset upload routes"
```

---

### Task 3: Link episodes to series

**Files:**
- Modify: `saas/routers/episodes.py`
- Test: `tests/saas/test_episodes_routes.py` (append)

**Interfaces:**
- Consumes: `EpisodeIn.series_id` (Task 1), `Series` model.
- Produces: `POST /episodes` accepts `series_id` and 404s if the series belongs to another user; `GET /episodes?series_id=N` filters. `EpisodeOut.series_id` populated.

- [ ] **Step 1: Write the failing tests** (append to `tests/saas/test_episodes_routes.py`)

```python
def test_create_episode_in_series_and_filter(client):
    headers = _signup_and_auth_headers(client, email="series-owner@example.com")
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]

    ep = client.post("/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers)
    assert ep.status_code == 201
    assert ep.json()["series_id"] == sid

    client.post("/episodes", json={"title": "standalone", "scenes": []}, headers=headers)
    filtered = client.get(f"/episodes?series_id={sid}", headers=headers)
    assert [e["title"] for e in filtered.json()] == ["EP1"]


def test_create_episode_rejects_foreign_series(client):
    headers_a = _signup_and_auth_headers(client, email="sa@example.com")
    headers_b = _signup_and_auth_headers(client, email="sb@example.com")
    sid = client.post("/series", json={"name": "A's"}, headers=headers_a).json()["id"]

    response = client.post("/episodes", json={"title": "X", "series_id": sid, "scenes": []}, headers=headers_b)
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/saas/test_episodes_routes.py -v -k series`
Expected: FAIL (`series_id` ignored / missing from response).

- [ ] **Step 3: Implement**

In `saas/routers/episodes.py`:

- Import `Series` in the models import line.
- In `create_episode`, after the plan-limit check, add:

```python
    if payload.series_id is not None:
        series = db.query(Series).filter_by(id=payload.series_id, user_id=current_user.id).one_or_none()
        if series is None:
            raise HTTPException(status_code=404, detail="Series not found")
```

and pass `series_id=payload.series_id` into the `Episode(...)` constructor.

- Change `list_episodes` to accept an optional filter:

```python
@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    series_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Episode]:
    query = db.query(Episode).filter_by(user_id=current_user.id)
    if series_id is not None:
        query = query.filter_by(series_id=series_id)
    return query.all()
```

- [ ] **Step 4: Run tests, remove any xfail from Task 2**

Run: `py -m pytest tests/saas/test_episodes_routes.py tests/saas/test_series_routes.py -v`
Expected: all PASS. If Task 2 marked `test_episode_count_reflects_linked_episodes` as xfail, remove the marker now and re-run.

- [ ] **Step 5: Commit**

```powershell
git add saas/routers/episodes.py tests/saas/test_episodes_routes.py tests/saas/test_series_routes.py
git commit -m "feat(episodes): link episodes to series with ownership check and filter"
```

---

### Task 4: Script-analysis module (Claude API)

**Files:**
- Create: `saas/script_analysis.py`
- Modify: `requirements.txt` (add `anthropic>=0.60.0`)
- Modify: `.env.example` (add `ANTHROPIC_API_KEY=`)
- Test: `tests/saas/test_script_analysis.py`

**Interfaces:**
- Produces:
  - `class ScriptAnalysisError(Exception)` — raised on API failure, refusal, or unparseable output.
  - `analyze_script(script_text: str, assets: list[dict]) -> list[dict]` where each input asset is `{"name": str, "description": str}` and each returned scene is `{"narration_text": str, "matched_asset_name": str | None, "asset_brief": str | None}`. Exactly one of `matched_asset_name` / `asset_brief` is non-null per scene.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_script_analysis.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from saas.script_analysis import ScriptAnalysisError, analyze_script


def _fake_response(payload: dict, stop_reason: str = "end_turn"):
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[block], stop_reason=stop_reason)


VALID_PAYLOAD = {
    "scenes": [
        {"narration_text": "A quiet morning.", "matched_asset_name": "bedroom_morning", "asset_brief": None},
        {"narration_text": "Sirens outside.", "matched_asset_name": None,
         "asset_brief": "City street at dawn with red and blue siren lights, stick-figure style"},
    ]
}


@patch("saas.script_analysis._client")
def test_analyze_script_returns_scenes(mock_client):
    mock_client.return_value.messages.create.return_value = _fake_response(VALID_PAYLOAD)

    scenes = analyze_script("script text", [{"name": "bedroom_morning", "description": "Bedroom at dawn"}])

    assert len(scenes) == 2
    assert scenes[0]["matched_asset_name"] == "bedroom_morning"
    assert scenes[1]["asset_brief"].startswith("City street")

    kwargs = mock_client.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-8"
    assert "bedroom_morning" in kwargs["messages"][0]["content"]


@patch("saas.script_analysis._client")
def test_analyze_script_raises_on_refusal(mock_client):
    mock_client.return_value.messages.create.return_value = _fake_response({}, stop_reason="refusal")
    with pytest.raises(ScriptAnalysisError):
        analyze_script("script", [])


@patch("saas.script_analysis._client")
def test_analyze_script_raises_on_invalid_json(mock_client):
    block = SimpleNamespace(type="text", text="not json at all")
    mock_client.return_value.messages.create.return_value = SimpleNamespace(
        content=[block], stop_reason="end_turn"
    )
    with pytest.raises(ScriptAnalysisError):
        analyze_script("script", [])


def test_analyze_script_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ScriptAnalysisError, match="ANTHROPIC_API_KEY"):
        analyze_script("script", [])
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/saas/test_script_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.script_analysis'`

- [ ] **Step 3: Install the SDK and write the module**

Run `py -m pip install "anthropic>=0.60.0"` and add `anthropic>=0.60.0` to `requirements.txt`. Add `ANTHROPIC_API_KEY=` to `.env.example` (and to the local `.env` — value supplied by the project owner).

Create `saas/script_analysis.py`:

```python
"""Split a raw episode script into scenes with matched/missing series assets via Claude."""
from __future__ import annotations

import json
import os

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration_text": {"type": "string"},
                    "matched_asset_name": {"type": ["string", "null"]},
                    "asset_brief": {"type": ["string", "null"]},
                },
                "required": ["narration_text", "matched_asset_name", "asset_brief"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scenes"],
    "additionalProperties": False,
}

PROMPT = """You are a video-production assistant for a narrated stick-figure YouTube series.
Split the script below into scenes for a slideshow-style video (one image per scene).

Rules:
- Each scene's narration_text is 1-3 sentences of the script, verbatim in the script's language.
- Cover the whole script in order; do not invent or drop content.
- For each scene, pick the best matching asset from the catalog by name and set matched_asset_name.
- If no catalog asset fits, set matched_asset_name to null and write asset_brief instead:
  an English image-generation prompt describing the needed image in the series' stick-figure style.
- Exactly one of matched_asset_name / asset_brief must be non-null per scene.

Asset catalog (name: description):
{catalog}

Script:
{script}"""


class ScriptAnalysisError(Exception):
    pass


def _client():
    import anthropic

    return anthropic.Anthropic()


def analyze_script(script_text: str, assets: list[dict]) -> list[dict]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ScriptAnalysisError("ANTHROPIC_API_KEY is not set — see SETUP.md")

    catalog = "\n".join(f"- {a['name']}: {a['description']}" for a in assets) or "(no assets yet)"
    try:
        response = _client().messages.create(
            model="claude-opus-4-8",
            max_tokens=16000,
            output_config={"format": {"type": "json_schema", "schema": SCENE_SCHEMA}},
            messages=[{"role": "user", "content": PROMPT.format(catalog=catalog, script=script_text)}],
        )
    except Exception as e:  # anthropic APIError and network failures
        raise ScriptAnalysisError(str(e)) from e

    if response.stop_reason == "refusal":
        raise ScriptAnalysisError("Model refused the request")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        scenes = json.loads(text)["scenes"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ScriptAnalysisError(f"Unparseable model output: {e}") from e
    if not scenes:
        raise ScriptAnalysisError("Model returned no scenes")
    return scenes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_script_analysis.py -v`
Expected: PASS. Note the tests patch `saas.script_analysis._client`, so no real API key or network is used; `test_analyze_script_requires_api_key` must not be patched. The first three tests need `ANTHROPIC_API_KEY` set — add `monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")` via an autouse fixture in this test file:

```python
@pytest.fixture(autouse=True)
def _api_key(request, monkeypatch):
    if "requires_api_key" not in request.node.name:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
```

- [ ] **Step 5: Commit**

```powershell
git add saas/script_analysis.py tests/saas/test_script_analysis.py requirements.txt .env.example
git commit -m "feat(agent): add Claude-based script analysis module"
```

---

### Task 5: Analyze-script endpoint

**Files:**
- Modify: `saas/routers/episodes.py`
- Modify: `saas/schemas.py`
- Test: `tests/saas/test_episodes_routes.py` (append)

**Interfaces:**
- Consumes: `analyze_script` / `ScriptAnalysisError` (Task 4), `SeriesAsset` (Task 1).
- Produces: `POST /episodes/{episode_id}/analyze-script` with body `{"script": str}` (schema `AnalyzeScriptIn`). Behavior: episode must be owned and `status == "draft"` else 409 `ERR_EPISODE_NOT_DRAFT`; replaces all existing scenes; scenes matched to a series asset get that asset's `object_key` copied into `scene.asset_object_key`; unmatched scenes get `asset_brief`. Returns `EpisodeOut`. On `ScriptAnalysisError` → 502 `ERR_SCRIPT_ANALYSIS_FAILED` (episode unchanged).

- [ ] **Step 1: Write the failing tests** (append to `tests/saas/test_episodes_routes.py`)

```python
from unittest.mock import patch as _patch


def _series_with_asset(client, headers):
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    from saas.db import get_db as _gd  # insert asset directly; upload route needs S3
    db = next(iter(app.dependency_overrides[_gd]()))
    from saas.models import SeriesAsset
    asset = SeriesAsset(series_id=sid, kind="location", name="bedroom_morning",
                        description="Bedroom at dawn", object_key=f"series/{sid}/assets/1.png")
    db.add(asset)
    db.commit()
    return sid


@_patch("saas.routers.episodes.analyze_script")
def test_analyze_script_replaces_scenes_and_matches_assets(mock_analyze, client):
    headers = _signup_and_auth_headers(client, email="an1@example.com")
    sid = _series_with_asset(client, headers)
    ep = client.post("/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers).json()

    mock_analyze.return_value = [
        {"narration_text": "Morning.", "matched_asset_name": "bedroom_morning", "asset_brief": None},
        {"narration_text": "Sirens.", "matched_asset_name": None, "asset_brief": "Street with sirens"},
    ]

    response = client.post(f"/episodes/{ep['id']}/analyze-script", json={"script": "raw script"}, headers=headers)

    assert response.status_code == 200
    scenes = response.json()["scenes"]
    assert scenes[0]["asset_object_key"] == f"series/{sid}/assets/1.png"
    assert scenes[0]["asset_brief"] is None
    assert scenes[1]["asset_object_key"] is None
    assert scenes[1]["asset_brief"] == "Street with sirens"


@_patch("saas.routers.episodes.analyze_script")
def test_analyze_script_requires_draft_status(mock_analyze, client):
    headers = _signup_and_auth_headers(client, email="an2@example.com")
    ep = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()
    # flip status directly in DB
    from saas.db import get_db as _gd
    db = next(iter(app.dependency_overrides[_gd]()))
    from saas.models import Episode
    db.query(Episode).filter_by(id=ep["id"]).update({"status": "built"})
    db.commit()

    response = client.post(f"/episodes/{ep['id']}/analyze-script", json={"script": "s"}, headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "ERR_EPISODE_NOT_DRAFT"
    mock_analyze.assert_not_called()


@_patch("saas.routers.episodes.analyze_script")
def test_analyze_script_maps_failure_to_502(mock_analyze, client):
    from saas.script_analysis import ScriptAnalysisError
    mock_analyze.side_effect = ScriptAnalysisError("boom")
    headers = _signup_and_auth_headers(client, email="an3@example.com")
    ep = client.post("/episodes", json={"title": "EP1", "scenes": [{"narration_text": "keep me"}]}, headers=headers).json()

    response = client.post(f"/episodes/{ep['id']}/analyze-script", json={"script": "s"}, headers=headers)

    assert response.status_code == 502
    assert response.json()["detail"] == "ERR_SCRIPT_ANALYSIS_FAILED"
    unchanged = client.get(f"/episodes/{ep['id']}", headers=headers).json()
    assert unchanged["scenes"][0]["narration_text"] == "keep me"
```

- [ ] **Step 2: Run to verify they fail**

Run: `py -m pytest tests/saas/test_episodes_routes.py -v -k analyze`
Expected: FAIL with 404 (route missing).

- [ ] **Step 3: Implement**

In `saas/schemas.py` add:

```python
class AnalyzeScriptIn(BaseModel):
    script: str
```

In `saas/routers/episodes.py`:

- Add imports: `from ..script_analysis import ScriptAnalysisError, analyze_script`, `SeriesAsset` in the models import, `AnalyzeScriptIn` in the schemas import.
- Add the route:

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

    series_assets: dict[str, SeriesAsset] = {}
    if episode.series_id is not None:
        rows = db.query(SeriesAsset).filter_by(series_id=episode.series_id).all()
        series_assets = {a.name: a for a in rows}

    try:
        scenes = analyze_script(
            payload.script,
            [{"name": a.name, "description": a.description} for a in series_assets.values()],
        )
    except ScriptAnalysisError:
        raise HTTPException(status_code=502, detail="ERR_SCRIPT_ANALYSIS_FAILED")

    episode.scenes.clear()
    for index, scene in enumerate(scenes):
        matched = series_assets.get(scene.get("matched_asset_name") or "")
        episode.scenes.append(
            Scene(
                order_index=index,
                narration_text=scene["narration_text"],
                asset_object_key=matched.object_key if matched else None,
                asset_brief=None if matched else scene.get("asset_brief"),
            )
        )
    db.commit()
    db.refresh(episode)
    return episode
```

- [ ] **Step 4: Run the full backend suite**

Run: `py -m pytest tests/saas -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```powershell
git add saas/routers/episodes.py saas/schemas.py tests/saas/test_episodes_routes.py
git commit -m "feat(agent): add POST /episodes/{id}/analyze-script endpoint"
```

---

### Task 6: Frontend — Series pages + sidebar link

**Files:**
- Create: `frontend/src/app/dashboard/series/page.tsx`
- Create: `frontend/src/app/dashboard/series/[id]/page.tsx`
- Modify: `frontend/src/app/dashboard/layout.tsx` (add "Series" nav item)
- Test: `frontend/src/__tests__/series.test.tsx`

**Interfaces:**
- Consumes: `GET/POST /series`, `GET /series/{id}`, `GET/POST /series/{id}/assets`, `GET /episodes?series_id=` via `lib/api.ts`; multipart upload via raw `fetch("/api/series/{id}/assets", ...)` with Bearer token (same pattern as the episode asset upload).
- Produces: `/dashboard/series` list page with inline create form (name + description); `/dashboard/series/[id]` detail page with asset grid (upload: file + kind select [character|location|object|other] + name + description), episodes list, and a "New episode in this series" link to `/dashboard/episodes/new?series_id={id}`.

Follow the existing visual idiom exactly: `"use client"` pages, Tailwind classes plus inline `style` hex colors (`#EDEDEF` headings, `#8A8F98` secondary text, indigo gradient primary buttons), `api`/`ApiError` from `@/lib/api`, redirect to `/login` on 401 (see `dashboard/page.tsx` for the reference pattern).

- [ ] **Step 1: Write the failing Jest test**

Create `frontend/src/__tests__/series.test.tsx` (mirror the structure of `__tests__/dashboard.test.tsx` — mock `@/lib/api`):

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import SeriesPage from "@/app/dashboard/series/page";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn() },
  ApiError: class ApiError extends Error {
    constructor(public status: number, public detail: string) { super(detail); }
  },
}));

describe("SeriesPage", () => {
  it("lists series returned by the API", async () => {
    (api.get as jest.Mock).mockResolvedValue([
      { id: 1, name: "Zombie apocalypse", description: "", style: {}, episode_count: 3 },
    ]);
    render(<SeriesPage />);
    await waitFor(() => expect(screen.getByText("Zombie apocalypse")).toBeInTheDocument());
    expect(screen.getByText(/3 episode/)).toBeInTheDocument();
  });

  it("shows the empty state when there are no series", async () => {
    (api.get as jest.Mock).mockResolvedValue([]);
    render(<SeriesPage />);
    await waitFor(() => expect(screen.getByText(/No series yet/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- series` (from `frontend/`)
Expected: FAIL (module `@/app/dashboard/series/page` not found).

- [ ] **Step 3: Build the pages**

`frontend/src/app/dashboard/series/page.tsx` — list + create. Core structure (style it per the idiom above):

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

export default function SeriesPage() {
  const [series, setSeries] = useState<Series[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const load = () =>
    api.get<Series[]>("/series").then(setSeries).catch((err) => {
      if (err instanceof ApiError && err.status === 401) window.location.href = "/login";
      else setError("Failed to load series.");
    });

  useEffect(() => { load().finally(() => setLoading(false)); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    try {
      await api.post<Series>("/series", { name, description });
      setName(""); setDescription("");
      await load();
    } catch { setError("Failed to create series."); }
    finally { setCreating(false); }
  }

  // Render: header "Series" + count, create form (input name, input description,
  // submit button "New series"), list of Link cards to /dashboard/series/{id}
  // showing name, description, "{episode_count} episode(s)".
  // Empty state text: "No series yet — create your first one above."
  // Loading and error states as in dashboard/page.tsx.
}
```

Complete the render JSX following `dashboard/page.tsx` (header block, card list with hover states, `STATUS_CONFIG`-style inline colors are not needed here).

`frontend/src/app/dashboard/series/[id]/page.tsx` — detail. Requirements:

- Load `GET /series/{id}`, `GET /series/{id}/assets`, `GET /episodes?series_id={id}` on mount (`useParams()` for id).
- Asset upload form: `<input type="file">`, `<select>` kind (character/location/object/other), name input (default to file basename without extension), description textarea, submit posts `FormData` (`file`, `kind`, `name`, `description`) to `` `/api/series/${id}/assets` `` with `Authorization: Bearer ${localStorage.getItem("access_token")}` — same raw-fetch pattern as `handleAssetUpload` in `episodes/[id]/page.tsx`.
- Asset grid: card per asset with kind badge, name, description.
- Episodes section: list linking to `/dashboard/episodes/{id}`, plus a prominent Link button "New episode in this series" → `/dashboard/episodes/new?series_id={id}`.

`frontend/src/app/dashboard/layout.tsx` — add a nav item labeled `Series` pointing at `/dashboard/series`, placed between the existing `Episodes` and `YouTube` items, using the same active-state styling as its siblings (read the file and copy the `Episodes` item's markup).

- [ ] **Step 4: Run tests + typecheck**

Run: `npm test -- series` then `npx tsc --noEmit` (from `frontend/`)
Expected: tests PASS, no type errors.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/app/dashboard/series frontend/src/app/dashboard/layout.tsx frontend/src/__tests__/series.test.tsx
git commit -m "feat(frontend): add series list/detail pages and sidebar link"
```

---

### Task 7: Frontend — paste-script flow + missing-asset checklist

**Files:**
- Modify: `frontend/src/app/dashboard/episodes/new/page.tsx`
- Modify: `frontend/src/app/dashboard/episodes/[id]/page.tsx`
- Test: `frontend/src/__tests__/new-episode.test.tsx` (append)

**Interfaces:**
- Consumes: `POST /episodes` with `series_id`, `POST /episodes/{id}/analyze-script`, `SceneOut.asset_brief`.
- Produces: new-episode page supports `?series_id=` and a "Paste script" mode; episode detail page shows the asset brief under scenes that miss an asset.

- [ ] **Step 1: Write the failing test** (append to `frontend/src/__tests__/new-episode.test.tsx`, following its existing mocking style)

```tsx
it("creates an episode from a pasted script via analyze-script", async () => {
  (api.post as jest.Mock)
    .mockResolvedValueOnce({ id: 7 })                          // POST /episodes
    .mockResolvedValueOnce({ id: 7, scenes: [] });             // POST /episodes/7/analyze-script
  render(<NewEpisodePage />);

  fireEvent.click(screen.getByText(/Paste script/i));
  fireEvent.change(screen.getByLabelText(/Title/i), { target: { value: "EP1" } });
  fireEvent.change(screen.getByPlaceholderText(/Paste your full script/i), {
    target: { value: "Long script..." },
  });
  fireEvent.click(screen.getByRole("button", { name: /Analyze script/i }));

  await waitFor(() => {
    expect(api.post).toHaveBeenCalledWith("/episodes", expect.objectContaining({ title: "EP1", scenes: [] }));
    expect(api.post).toHaveBeenCalledWith("/episodes/7/analyze-script", { script: "Long script..." });
  });
});
```

Adjust `useRouter`/`useSearchParams` mocks to match what the file already mocks (it uses `next/navigation`).

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- new-episode`
Expected: FAIL ("Paste script" toggle does not exist).

- [ ] **Step 3: Implement**

`episodes/new/page.tsx`:

- Read `series_id` from `useSearchParams()`; if present include it in the create payload and show the series name (fetch `GET /series/{id}`).
- Add a mode toggle at the top of the form: `Manual scenes` (existing behavior) | `Paste script`.
- Paste-script mode: title/description/tags inputs stay; the scenes editor is replaced by one `<textarea placeholder="Paste your full script...">` and the submit button reads `Analyze script`. Submit flow: `POST /episodes` with `scenes: []` (+ `series_id` if set) → `POST /episodes/{id}/analyze-script` with `{ script }` → `router.push(\`/dashboard/episodes/${id}\`)`. On analyze failure (`ApiError` with detail `ERR_SCRIPT_ANALYSIS_FAILED`), still navigate to the episode page but show a query-less fallback is unnecessary — set an error state: "AI analysis failed — the episode was created empty, add scenes manually."
- Manual mode is unchanged.

`episodes/[id]/page.tsx`:

- Add `asset_brief: string | null` to the local `Scene` interface.
- In the scene card, when `scene.asset_object_key` is null and `scene.asset_brief` is set, render a highlighted block: label `Ảnh cần tạo` (amber accent `#F59E0B`), the `asset_brief` text, and a "Copy prompt" button (`navigator.clipboard.writeText(scene.asset_brief)`).
- Above the scene list, when any scene misses an asset, show a summary line: `X scenes still need an image — briefs are shown below each scene.`

- [ ] **Step 4: Run tests + typecheck + Playwright smoke**

Run: `npm test` then `npx tsc --noEmit`, both from `frontend/`.
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```powershell
git add "frontend/src/app/dashboard/episodes/new/page.tsx" "frontend/src/app/dashboard/episodes/[id]/page.tsx" frontend/src/__tests__/new-episode.test.tsx
git commit -m "feat(frontend): paste-script analyze flow and missing-asset checklist"
```

---

### Task 8: Produce EP 1 for real (end-to-end checkpoint — needs the project owner)

**Files:** none (manual verification per spec section "Kiểm chứng end-to-end", items 1-2).

This task exercises the real system. It needs two inputs only the project owner can provide: a funded `ANTHROPIC_API_KEY`, a working `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` (chốt giọng sau khi chạy so sánh tiếng Việt — see spec decision #4), and the EP 1 script text. **Stop and ask for them if missing.**

- [ ] **Step 1: Start the stack** — `docker compose up -d`; API via `py -c "from dotenv import load_dotenv; load_dotenv(); import uvicorn; uvicorn.run('saas.main:app', host='127.0.0.1', port=8000)"`; worker via `py -c "from dotenv import load_dotenv; load_dotenv()" ; py -m celery -A saas.celery_app.celery_app worker --loglevel=info --pool=solo` (worker also needs the .env loaded — export vars in the shell or use dotenv the same way); frontend `npm run dev`. Note: local Postgres runs on port **5433** (see docker-compose.override.yml).
- [ ] **Step 2: Voice comparison (spec decision #4)** — write a throwaway script that sends the same Vietnamese paragraph (from the EP 1 script) to ElevenLabs with 2-3 candidate voices, save mp3s, let the owner pick. Record the chosen `ELEVENLABS_VOICE_ID` in `.env` and in the series `style`.
- [ ] **Step 3: Create the series in the UI** — name "What if the world apocalypse with zombies", style gồm voice đã chốt. Upload all images from `D:\Video\Seri 1\EP 1` (4 batch folders) as series assets with kind + name + a one-line English description each (the description quality drives matching accuracy — write real ones).
- [ ] **Step 4: Create EP 1 via paste-script** — new episode in the series, paste the owner's script, run Analyze. Verify: scenes cover the whole script, matched assets look right, briefs for missing images read like usable image prompts.
- [ ] **Step 5: Fill gaps** — owner generates any missing images (using the briefs) and uploads them per scene (or as series assets + re-analyze).
- [ ] **Step 6: Build** — click Build episode; watch the Celery worker; when done, preview the mp4 from the episode page. Verify voice, captions, Ken Burns motion, scene order.
- [ ] **Step 7: Review with the owner** — the owner watches EP 1 end-to-end and decides: publish manually to YouTube (API upload optional here — spec defers YouTube automation), iterate on script/images, or adjust engine config (caption size, zoom speed in `config.yaml`).
- [ ] **Step 8: EP 2 and EP 3** — repeat Steps 4-7 for the next two episodes (owner supplies scripts; series assets are already in place, so these validate the reuse story). The spec's Phase 1 done-definition is 3 finished episodes, not 1.
- [ ] **Step 9: Record learnings** — append a "Phase 1 findings" section to the spec noting anything that must feed Phase 2 (effects wishlist, TTS verdict, analysis prompt tweaks). Commit docs.

---

## Sequence summary

| # | Files | Deliverable |
|---|---|---|
| 1 | models.py, schemas.py | Series/SeriesAsset tables, episode/scene columns |
| 2 | routers/series.py, storage.py, main.py | Series CRUD + shared asset upload |
| 3 | routers/episodes.py | Episode↔series link + filter |
| 4 | script_analysis.py, requirements.txt | Claude script→scenes module |
| 5 | routers/episodes.py, schemas.py | POST /episodes/{id}/analyze-script |
| 6 | dashboard/series pages, layout.tsx | Series UI |
| 7 | episodes/new + [id] pages | Paste-script flow + brief checklist |
| 8 | — (manual, with owner) | EP 1 built for real; findings recorded |
