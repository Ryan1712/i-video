# Object Storage Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace local-disk storage for scene assets and episode build output (`saas/storage.py`, `UPLOADS_DIR`/`EPISODES_DIR`) with S3-compatible object storage (MinIO locally, any S3-compatible service in production), with no other behavior change.

**Architecture:** `saas/object_storage.py` is a generic boto3 wrapper (`ensure_bucket`, `upload_bytes`, `download_to_path`, `presigned_url`), mockable with `moto` in tests. `saas/storage.py` keeps its existing two-function-call shape (`save_asset`, now plus `save_output`, `presigned_asset_url`, `presigned_output_url`) as a thin domain wrapper over `object_storage.py` — callers in `episodes.py` and `tasks.py` don't need to know S3 exists. `Scene.asset_path`/`Episode.output_path` are renamed to `asset_object_key`/`output_object_key` since they now hold S3 keys, not filesystem paths. The video-build engine (`agent_video/*`) is untouched — it only ever sees local file paths inside the existing temp dir.

**Tech Stack:** boto3 (S3 client), moto (S3 mocking in tests, `@mock_aws`), MinIO (local S3-compatible dev server via Docker Compose).

## Global Constraints

- No bytes touch local disk during scene-asset upload — `object_storage.upload_bytes` is called directly from the bytes read off the `UploadFile`.
- The build job (`saas/tasks.py::run_build`) still creates a local `temp_dir` exactly as today; only the *source* of scene assets (download from S3 instead of resolving a local path) and the *destination* of the final mp4 (upload to S3 instead of `shutil.copyfile` into `EPISODES_DIR`) change. The engine call signatures (`build_scene_clip`, `build_episode`, `synthesize_scene`, `get_audio_duration`) are unchanged.
- `download_to_path`/`ensure_bucket` failures propagate as today's generic exception path — no new error-handling branch in `run_build`.
- No Alembic/migration tool exists (tables created via `Base.metadata.create_all`) — column renames are plain SQLAlchemy model edits; existing local dev DBs are dropped and recreated, per `SETUP.md` section 5.3.
- `moto`'s `@mock_aws` decorator means no real network calls in the test suite, consistent with how Stripe is already mocked (`unittest.mock.patch`).
- Reuse `tests/saas/conftest.py` fixtures (`db_session_factory`, `db_session`). Do not create a second DB setup or test-fixture file.
- Presigned URLs default to a 300-second expiry, generated fresh per request — never cached, no configurable per-caller expiry (out of scope for v1, per spec).

---

## File Structure

- Create: `saas/object_storage.py` — generic S3-compatible wrapper.
- Modify: `saas/storage.py` — rewrite to call `object_storage.py`; add `save_output`, `presigned_asset_url`, `presigned_output_url`; remove `get_asset_abs_path`.
- Modify: `saas/models.py` — rename `Scene.asset_path` → `asset_object_key`, `Episode.output_path` → `output_object_key`.
- Modify: `saas/schemas.py` — rename `SceneOut.asset_path` → `asset_object_key`, `EpisodeOut.output_path` → `output_object_key`; add `AssetUrlOut`, `OutputUrlOut`.
- Modify: `saas/routers/episodes.py` — update field references; add `GET /episodes/{episode_id}/scenes/{scene_id}/asset-url` and `GET /episodes/{episode_id}/output-url`.
- Modify: `saas/tasks.py` — use `object_storage.download_to_path` for scene assets, `storage.save_output` for the final mp4; remove `_episodes_dir`/`EPISODES_DIR`.
- Modify: `saas/main.py` — call `object_storage.ensure_bucket()` on FastAPI startup.
- Modify: `saas/celery_app.py` — call `object_storage.ensure_bucket()` on Celery `worker_ready`.
- Modify: `requirements.txt` — add `boto3`, `moto[s3]`.
- Modify: `.env.example` — add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`.
- Modify: `docker-compose.yml` — add `minio` service.
- Modify: `SETUP.md` — section 5 gains MinIO setup steps.
- Test: `tests/saas/test_object_storage.py` (new), `tests/saas/test_storage.py` (rewritten), `tests/saas/test_models.py` (field renames), `tests/saas/test_episodes_routes.py` (field renames + new routes), `tests/saas/test_tasks.py` (rewritten).

---

### Task 1: `object_storage.py` — generic S3 wrapper

**Files:**
- Modify: `requirements.txt`
- Create: `saas/object_storage.py`
- Test: `tests/saas/test_object_storage.py`

**Interfaces:**
- Produces: `get_s3_client() -> boto3.client`, `ensure_bucket() -> None`, `upload_bytes(key: str, content: bytes) -> None`, `download_to_path(key: str, local_path: str) -> None`, `presigned_url(key: str, expires_in: int = 300) -> str`.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt`:

```
boto3>=1.34.0
moto[s3]>=5.0.0
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing test**

```python
# tests/saas/test_object_storage.py
import os

import boto3
from moto import mock_aws


@mock_aws
def test_ensure_bucket_creates_bucket_if_missing(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket, get_s3_client

    ensure_bucket()

    client = get_s3_client()
    response = client.list_buckets()
    bucket_names = [b["Name"] for b in response["Buckets"]]
    assert "whatif-test-bucket" in bucket_names


@mock_aws
def test_ensure_bucket_is_idempotent(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket

    ensure_bucket()
    ensure_bucket()  # must not raise on the second call


@mock_aws
def test_upload_and_download_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import download_to_path, ensure_bucket, upload_bytes

    ensure_bucket()
    upload_bytes("episodes/1/scenes/2.png", b"fake-png-bytes")

    local_path = tmp_path / "downloaded.png"
    download_to_path("episodes/1/scenes/2.png", str(local_path))

    assert local_path.read_bytes() == b"fake-png-bytes"


@mock_aws
def test_presigned_url_contains_key_and_bucket(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket, presigned_url, upload_bytes

    ensure_bucket()
    upload_bytes("episodes/1/output.mp4", b"fake-mp4-bytes")

    url = presigned_url("episodes/1/output.mp4", expires_in=120)

    assert "whatif-test-bucket" in url
    assert "episodes/1/output.mp4" in url
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_object_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.object_storage'`

- [ ] **Step 4: Implement**

```python
# saas/object_storage.py
"""Generic S3-compatible object storage wrapper (boto3); mockable with moto in tests."""
from __future__ import annotations

import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def _bucket_name() -> str:
    name = os.environ.get("S3_BUCKET_NAME")
    if not name:
        raise RuntimeError("S3_BUCKET_NAME environment variable is not set")
    return name


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    client = get_s3_client()
    bucket = _bucket_name()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def upload_bytes(key: str, content: bytes) -> None:
    client = get_s3_client()
    client.put_object(Bucket=_bucket_name(), Key=key, Body=content)


def download_to_path(key: str, local_path: str) -> None:
    client = get_s3_client()
    client.download_file(_bucket_name(), key, local_path)


def presigned_url(key: str, expires_in: int = 300) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket_name(), "Key": key},
        ExpiresIn=expires_in,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_object_storage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt saas/object_storage.py tests/saas/test_object_storage.py
git commit -m "feat(storage): add S3-compatible object_storage wrapper"
```

---

### Task 2: Rewrite `saas/storage.py` over `object_storage.py`

**Files:**
- Modify: `saas/storage.py`
- Test: `tests/saas/test_storage.py` (rewritten)

**Interfaces:**
- Consumes: `object_storage.upload_bytes`, `object_storage.download_to_path`, `object_storage.presigned_url` (Task 1).
- Produces: `save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str`, `save_output(episode_id: int, local_mp4_path: str) -> str`, `presigned_asset_url(key: str) -> str`, `presigned_output_url(key: str) -> str`. All return/accept an S3 object key, never a local filesystem path.

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/saas/test_storage.py`:

```python
# tests/saas/test_storage.py
from moto import mock_aws


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


@mock_aws
def test_save_asset_uploads_and_returns_key(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_asset

    ensure_bucket()
    key = save_asset(episode_id=3, scene_id=7, filename="hero.png", content=b"fake-png-bytes")

    assert key == "episodes/3/scenes/7.png"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-png-bytes"


@mock_aws
def test_save_asset_preserves_extension(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket
    from saas.storage import save_asset

    ensure_bucket()
    key = save_asset(episode_id=1, scene_id=2, filename="photo.jpeg", content=b"x")

    assert key.endswith(".jpeg")


@mock_aws
def test_save_output_uploads_local_file_and_returns_key(tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_output

    ensure_bucket()
    local_path = tmp_path / "out.mp4"
    local_path.write_bytes(b"fake-mp4-bytes")

    key = save_output(episode_id=5, local_mp4_path=str(local_path))

    assert key == "episodes/5/output.mp4"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-mp4-bytes"


@mock_aws
def test_presigned_asset_url_and_presigned_output_url(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes
    from saas.storage import presigned_asset_url, presigned_output_url

    ensure_bucket()
    upload_bytes("episodes/1/scenes/2.png", b"x")
    upload_bytes("episodes/1/output.mp4", b"y")

    asset_url = presigned_asset_url("episodes/1/scenes/2.png")
    output_url = presigned_output_url("episodes/1/output.mp4")

    assert "episodes/1/scenes/2.png" in asset_url
    assert "episodes/1/output.mp4" in output_url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_storage.py -v`
Expected: FAIL with `ImportError: cannot import name 'save_output'`

- [ ] **Step 3: Implement**

Replace the entire contents of `saas/storage.py`:

```python
# saas/storage.py
"""Domain-specific S3 key naming for scene assets and episode output, thin wrapper over object_storage.py."""
from __future__ import annotations

import os

from .object_storage import presigned_url, upload_bytes


def save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    key = f"episodes/{episode_id}/scenes/{scene_id}{ext}"
    upload_bytes(key, content)
    return key


def save_output(episode_id: int, local_mp4_path: str) -> str:
    key = f"episodes/{episode_id}/output.mp4"
    with open(local_mp4_path, "rb") as f:
        upload_bytes(key, f.read())
    return key


def presigned_asset_url(key: str) -> str:
    return presigned_url(key)


def presigned_output_url(key: str) -> str:
    return presigned_url(key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_storage.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/storage.py tests/saas/test_storage.py
git commit -m "feat(storage): rewrite storage.py over the S3 object_storage wrapper"
```

---

### Task 3: Rename model/schema fields, update episode routes, add presigned-URL routes

**Files:**
- Modify: `saas/models.py`
- Modify: `saas/schemas.py`
- Modify: `saas/routers/episodes.py`
- Test: `tests/saas/test_models.py`, `tests/saas/test_episodes_routes.py`

**Interfaces:**
- Consumes: `storage.save_asset`, `storage.presigned_asset_url`, `storage.presigned_output_url` (Task 2).
- Produces: `Scene.asset_object_key: str | None`, `Episode.output_object_key: str | None`. `SceneOut.asset_object_key`, `EpisodeOut.output_object_key`. `AssetUrlOut(url: str)`, `OutputUrlOut(url: str)`. Routes: `GET /episodes/{episode_id}/scenes/{scene_id}/asset-url`, `GET /episodes/{episode_id}/output-url`.

- [ ] **Step 1: Write the failing test**

Edit `tests/saas/test_models.py` — replace the two renamed-field assertions:

```python
    fetched = db_session.query(Episode).filter_by(title="What If The Moon Disappeared").one()
    assert fetched.status == "draft"
    assert fetched.output_object_key is None
    assert len(fetched.scenes) == 2
    assert fetched.scenes[0].narration_text == "Scene one text"
    assert fetched.scenes[0].asset_object_key is None
```

Edit `tests/saas/test_episodes_routes.py` — replace `test_upload_scene_asset_sets_asset_path` and add the two new route tests (remove the `monkeypatch.setenv("UPLOADS_DIR", ...)` lines from this and the other two tests in the file that still set it, since that env var no longer exists):

```python
def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


@mock_aws
def test_upload_scene_asset_sets_asset_object_key(client, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket

    ensure_bucket()
    headers = _signup_and_auth_headers(client, email="uploader@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]},
        headers=headers,
    ).json()
    scene_id = created["scenes"][0]["id"]

    response = client.post(
        f"/episodes/{created['id']}/scenes/{scene_id}/asset",
        files={"file": ("hero.png", b"fake-png-bytes", "image/png")},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["asset_object_key"].endswith(".png")

    refetched = client.get(f"/episodes/{created['id']}", headers=headers).json()
    assert refetched["scenes"][0]["asset_object_key"] == response.json()["asset_object_key"]


@mock_aws
def test_get_scene_asset_url_returns_presigned_url(client, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket

    ensure_bucket()
    headers = _signup_and_auth_headers(client, email="asseturl@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]},
        headers=headers,
    ).json()
    scene_id = created["scenes"][0]["id"]
    client.post(
        f"/episodes/{created['id']}/scenes/{scene_id}/asset",
        files={"file": ("hero.png", b"fake-bytes", "image/png")},
        headers=headers,
    )

    response = client.get(f"/episodes/{created['id']}/scenes/{scene_id}/asset-url", headers=headers)

    assert response.status_code == 200
    assert "url" in response.json()


def test_get_scene_asset_url_requires_ownership(client):
    headers_a = _signup_and_auth_headers(client, email="ownera@example.com")
    headers_b = _signup_and_auth_headers(client, email="ownerb@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]},
        headers=headers_a,
    ).json()
    scene_id = created["scenes"][0]["id"]

    response = client.get(f"/episodes/{created['id']}/scenes/{scene_id}/asset-url", headers=headers_b)

    assert response.status_code == 404


def test_get_output_url_returns_404_when_not_built(client):
    headers = _signup_and_auth_headers(client, email="nooutput@example.com")
    created = client.post("/episodes", json={"title": "Ep", "scenes": []}, headers=headers).json()

    response = client.get(f"/episodes/{created['id']}/output-url", headers=headers)

    assert response.status_code == 404
```

Add `from moto import mock_aws` to the imports at the top of `tests/saas/test_episodes_routes.py`. In `test_trigger_build_enqueues_job_when_all_assets_present` (the only other test in this file that sets `UPLOADS_DIR`), remove `monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))` and instead add `_set_s3_env(monkeypatch)` plus the `@mock_aws` decorator and `from saas.object_storage import ensure_bucket; ensure_bucket()` before the upload call (it currently uploads a real asset, which now needs S3).

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_models.py tests/saas/test_episodes_routes.py -v`
Expected: FAIL — `AttributeError: 'Episode' object has no attribute 'output_object_key'` (model not renamed yet), and route 404/missing field errors.

- [ ] **Step 3: Implement**

In `saas/models.py`, rename the two columns:

```python
    output_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
```
(replaces `output_path` on `Episode`)

```python
    asset_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
```
(replaces `asset_path` on `Scene`)

In `saas/schemas.py`, rename the matching fields on `SceneOut` and `EpisodeOut` (`asset_path` → `asset_object_key`, `output_path` → `output_object_key`), and add:

```python
class AssetUrlOut(BaseModel):
    url: str


class OutputUrlOut(BaseModel):
    url: str
```

Replace `saas/routers/episodes.py` in full:

```python
"""Episode and scene CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..billing.limits import PlanLimitError, check_episode_limit
from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Job, Scene, User
from ..schemas import AssetUrlOut, EpisodeIn, EpisodeOut, JobOut, OutputUrlOut, SceneOut
from ..storage import presigned_asset_url, presigned_output_url, save_asset
from ..tasks import build_episode_task

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=EpisodeOut, status_code=201)
def create_episode(
    payload: EpisodeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    try:
        check_episode_limit(db, current_user)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=e.code)

    episode = Episode(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        status="draft",
    )
    for index, scene_in in enumerate(payload.scenes):
        episode.scenes.append(Scene(order_index=index, narration_text=scene_in.narration_text))

    db.add(episode)
    db.commit()
    return episode


@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Episode]:
    return db.query(Episode).filter_by(user_id=current_user.id).all()


def _get_owned_episode_or_404(episode_id: int, db: Session, current_user: User) -> Episode:
    episode = db.query(Episode).filter_by(id=episode_id, user_id=current_user.id).one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/{episode_id}", response_model=EpisodeOut)
def get_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    return _get_owned_episode_or_404(episode_id, db, current_user)


@router.post("/{episode_id}/scenes/{scene_id}/asset", response_model=SceneOut)
async def upload_scene_asset(
    episode_id: int,
    scene_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Scene:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    content = await file.read()
    key = save_asset(episode_id, scene_id, file.filename, content)
    scene.asset_object_key = key
    db.commit()
    return scene


@router.get("/{episode_id}/scenes/{scene_id}/asset-url", response_model=AssetUrlOut)
def get_scene_asset_url(
    episode_id: int,
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetUrlOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None or scene.asset_object_key is None:
        raise HTTPException(status_code=404, detail="Scene asset not found")
    return AssetUrlOut(url=presigned_asset_url(scene.asset_object_key))


@router.get("/{episode_id}/output-url", response_model=OutputUrlOut)
def get_output_url(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutputUrlOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if episode.output_object_key is None:
        raise HTTPException(status_code=404, detail="Episode output not built yet")
    return OutputUrlOut(url=presigned_output_url(episode.output_object_key))


@router.post("/{episode_id}/build", response_model=JobOut, status_code=202)
def trigger_build(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    try:
        check_episode_limit(db, current_user)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=e.code)

    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if any(scene.asset_object_key is None for scene in episode.scenes):
        raise HTTPException(status_code=400, detail="All scenes must have an uploaded asset before building")

    job = Job(episode_id=episode.id, type="build", status="queued")
    db.add(job)
    db.commit()

    build_episode_task.delay(job.id)
    return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_models.py tests/saas/test_episodes_routes.py -v`
Expected: PASS (all tests in both files)

- [ ] **Step 5: Commit**

```bash
git add saas/models.py saas/schemas.py saas/routers/episodes.py tests/saas/test_models.py tests/saas/test_episodes_routes.py
git commit -m "feat(episodes): rename asset/output fields to object keys, add presigned-url routes"
```

---

### Task 4: Update the build job to read/write S3 instead of local disk

**Files:**
- Modify: `saas/tasks.py`
- Test: `tests/saas/test_tasks.py` (rewritten)

**Interfaces:**
- Consumes: `object_storage.download_to_path` (Task 1), `storage.save_output` (Task 2), `Scene.asset_object_key`, `Episode.output_object_key` (Task 3).
- Produces: `run_build(job_id: int, session_factory: sessionmaker) -> None` (same signature as today).

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `tests/saas/test_tasks.py`:

```python
# tests/saas/test_tasks.py
from unittest.mock import patch

from moto import mock_aws

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def _make_episode_with_one_scene(db_session, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="e@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Test Episode", description="", tags="", status="ready")
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

    return episode.id, job.id


@mock_aws
def test_run_build_succeeds_and_updates_episode_and_job(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, monkeypatch)

    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")

    with patch("saas.tasks.synthesize_scene") as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip") as clip_mock, \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)) as build_ep_mock:
        run_build(job_id, db_session_factory)

    assert synth_mock.called
    assert clip_mock.called
    assert build_ep_mock.called

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "done"
    assert job.progress_pct == 100
    assert episode.status == "built"
    assert episode.output_object_key == f"episodes/{episode_id}/output.mp4"

    from saas.object_storage import get_s3_client

    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=episode.output_object_key)["Body"].read()
    assert body == b"fake-mp4-bytes"
    fresh.close()


@mock_aws
def test_run_build_marks_job_failed_on_exception(db_session, db_session_factory, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, monkeypatch)

    with patch("saas.tasks.synthesize_scene", side_effect=RuntimeError("ElevenLabs exploded")):
        run_build(job_id, db_session_factory)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "failed"
    assert "ElevenLabs exploded" in job.error_message
    assert episode.status == "draft"
    fresh.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_tasks.py -v`
Expected: FAIL — `TypeError: 'asset_object_key' is an invalid keyword argument for Scene` (model already renamed in Task 3, but `saas/tasks.py` still calls `get_asset_abs_path` which no longer exists) / `ImportError`.

- [ ] **Step 3: Implement**

Replace the entire contents of `saas/tasks.py`:

```python
"""Build job: assembles a temp video_dir from DB rows, then reuses the existing engine unchanged."""
from __future__ import annotations

import os
import shutil
import tempfile

from sqlalchemy.orm import sessionmaker

from agent_video.config import DEFAULT_CONFIG
from agent_video.image_builder import build_scene_clip
from agent_video.script_parser import Episode as EngineEpisode
from agent_video.script_parser import Scene as EngineScene
from agent_video.tts import get_audio_duration, synthesize_scene
from agent_video.video_builder import build_episode

from .celery_app import celery_app
from .db import init_session_factory
from .models import Episode, Job
from .object_storage import download_to_path
from .storage import save_output


def run_build(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
    job = None
    episode = None
    try:
        job = db.query(Job).filter_by(id=job_id).one()
        episode = db.query(Episode).filter_by(id=job.episode_id).one()

        job.status = "running"
        episode.status = "building"
        db.commit()

        temp_dir = tempfile.mkdtemp(prefix=f"ep{episode.id}_")
        try:
            os.makedirs(os.path.join(temp_dir, "audio"))
            os.makedirs(os.path.join(temp_dir, "output"))
            assets_dir = os.path.join(temp_dir, "assets")
            os.makedirs(assets_dir)

            engine_scenes = []
            for scene in episode.scenes:
                scene_name = f"scene_{scene.order_index:02d}"
                _, ext = os.path.splitext(scene.asset_object_key)
                local_asset_path = os.path.join(assets_dir, f"{scene_name}{ext}")
                download_to_path(scene.asset_object_key, local_asset_path)
                engine_scenes.append(
                    EngineScene(name=scene_name, asset=local_asset_path, text=scene.narration_text)
                )
            engine_episode = EngineEpisode(
                title=episode.title,
                description=episode.description,
                tags=[t.strip() for t in episode.tags.split(",") if t.strip()],
                scenes=engine_scenes,
            )

            config = DEFAULT_CONFIG
            audio_paths = []
            durations = []
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
            voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
            for scene in engine_episode.scenes:
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                synthesize_scene(scene.text, audio_path, api_key, voice_id)
                duration = get_audio_duration(audio_path)
                audio_paths.append(audio_path)
                durations.append(duration)

            clip_paths = []
            tmp_clip_dir = os.path.join(temp_dir, "output", "_tmp")
            for scene, duration in zip(engine_episode.scenes, durations):
                clip_path = os.path.join(temp_dir, "output", f"_clip_{scene.name}.mp4")
                build_scene_clip(scene.asset, duration, clip_path, tmp_clip_dir, config)
                clip_paths.append(clip_path)

            out_path = build_episode(engine_episode, clip_paths, audio_paths, durations, temp_dir, config)

            episode.output_object_key = save_output(episode.id, out_path)
            episode.status = "built"
            job.status = "done"
            job.progress_pct = 100
            db.commit()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        if job is not None:
            job.status = "failed"
            job.error_message = str(e)
        if episode is not None:
            episode.status = "draft"
        db.commit()
    finally:
        db.close()


@celery_app.task(name="saas.tasks.build_episode_task")
def build_episode_task(job_id: int) -> None:
    run_build(job_id, init_session_factory())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_tasks.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/tasks.py tests/saas/test_tasks.py
git commit -m "feat(tasks): build job reads scene assets from and writes output to S3"
```

---

### Task 5: MinIO infra, startup bucket creation, env/docs, full-suite verification

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `saas/main.py`
- Modify: `saas/celery_app.py`
- Modify: `SETUP.md`
- No new test file — Step 2 verifies the whole branch; Step 4 is a manual MinIO check.

**Interfaces:**
- Consumes: `object_storage.ensure_bucket` (Task 1).

- [ ] **Step 1: Add the MinIO service**

Append to `docker-compose.yml`:

```yaml
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: whatif
      MINIO_ROOT_PASSWORD: whatifsecret
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data
```

Add `miniodata:` to the `volumes:` block at the bottom of the file (alongside the existing `pgdata:`).

- [ ] **Step 2: Add the new env vars**

Append to `.env.example`:

```
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=whatif
S3_SECRET_KEY=whatifsecret
S3_BUCKET_NAME=whatif-assets
```

- [ ] **Step 3: Call `ensure_bucket()` on API and worker startup**

Modify `saas/main.py`:

```python
"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .object_storage import ensure_bucket
from .routers import (
    admin_audit,
    admin_plans,
    admin_settings,
    admin_transactions,
    admin_users,
    admin_vouchers,
    auth,
    billing,
    episodes,
    jobs,
)

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
app.include_router(admin_users.router)
app.include_router(admin_settings.router)
app.include_router(admin_audit.router)


@app.on_event("startup")
def _ensure_bucket_on_startup() -> None:
    ensure_bucket()
```

This only runs when `TestClient` is used as a context manager (`with TestClient(app) as client`); the existing test suite instantiates `TestClient(app)` directly without `with`, so none of today's tests trigger a real `ensure_bucket()` call.

Modify `saas/celery_app.py`:

```python
"""Celery app instance, Redis broker/backend."""
from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_ready

celery_app = Celery(
    "saas",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


@worker_ready.connect
def _ensure_bucket_on_worker_ready(**kwargs) -> None:
    from .object_storage import ensure_bucket

    ensure_bucket()
```

- [ ] **Step 4: Run the full test suite**

Run: `py -m pytest -q`
Expected: all tests pass (everything already on `master` plus this plan's rewritten/new tests).

- [ ] **Step 5: Document MinIO setup**

Append to `SETUP.md` section 5 (after the existing numbered steps, renumbering the existing step 6 "Open http://127.0.0.1:8000/docs..." to step 7 if needed — insert as the new step 6, immediately after starting Postgres/Redis):

```markdown
6. Start MinIO (already included in the `docker compose up -d` from step 1) and copy the new variables from `.env.example` into `.env`: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`. The bucket is created automatically on API/worker startup — no manual `mc` setup needed. The MinIO console is at http://localhost:9001 (login with `S3_ACCESS_KEY`/`S3_SECRET_KEY`) if you want to browse uploaded objects.
```

- [ ] **Step 6: Manual verification (not automated)**

1. `docker compose up -d minio`
2. Start the API (`py -m uvicorn saas.main:app --reload`) and a Celery worker (`py -m celery -A saas.celery_app.celery_app worker --loglevel=info --pool=solo`).
3. Sign up, create an episode with one scene, `POST` a scene asset via `/episodes/{id}/scenes/{scene_id}/asset`.
4. Confirm the object exists in the MinIO console at http://localhost:9001 under the `whatif-assets` bucket.
5. Trigger a build via `POST /episodes/{id}/build`, poll `/jobs/{id}` until `status == "done"`.
6. `GET /episodes/{id}/output-url` and confirm the returned presigned URL downloads a playable mp4.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example saas/main.py saas/celery_app.py SETUP.md
git commit -m "feat(storage): add MinIO to local infra, create bucket on API/worker startup"
```
