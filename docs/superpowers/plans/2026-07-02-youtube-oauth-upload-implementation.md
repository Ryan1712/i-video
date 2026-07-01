# YouTube OAuth Connect & Upload Job — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-07-02-youtube-oauth-upload-design.md`
**Baseline:** 154 tests passing on `master` (a8d7b1f)

## Global Constraints

- All S3 operations in tests use `@mock_aws` (moto) — no real network calls
- YouTube API calls in tests use `unittest.mock.patch` — no real Google calls
- OAuth `state` is a short-lived JWT signed with `JWT_SECRET`
- Refresh token encrypted at rest with Fernet (`TOKEN_ENCRYPTION_KEY` env var)
- Episode upload always sets `privacyStatus: "private"`
- `Episode.youtube_video_id` is new nullable column — no Alembic, `create_all` for dev
- One YouTube connection per user (UNIQUE on `user_id`) — upsert on re-connect
- `agent_video/youtube_uploader.py` is NOT modified
- Follow existing patterns: same error handling as `run_build`, same `_get_owned_episode_or_404` helper, same `@mock_aws` + `_set_s3_env` test patterns

---

## Task 1: Model + schema + encryption helper

**Files:**
- Modify: `saas/models.py`
- Modify: `saas/schemas.py`
- Create: `saas/youtube_auth.py`
- Modify: `requirements.txt`
- Modify: `tests/saas/test_models.py`

**Step 1: Add `cryptography` to requirements.txt**

```
cryptography>=42.0.0
```

**Step 2: Add `YouTubeConnection` model to `saas/models.py`**

```python
class YouTubeConnection(Base):
    __tablename__ = "youtube_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
```

Also add to `Episode`:
```python
youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

**Step 3: Create `saas/youtube_auth.py`**

```python
"""Fernet encryption for YouTube refresh tokens + OAuth flow helpers."""
from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY environment variable is not set")
    return Fernet(key.encode())


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
```

**Step 4: Add schemas to `saas/schemas.py`**

```python
class YouTubeStatusOut(BaseModel):
    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None

class YouTubeConnectOut(BaseModel):
    url: str
```

Also add `youtube_video_id: str | None = None` to `EpisodeOut`.

**Step 5: Write tests for `tests/saas/test_models.py`**

Add one test: `test_youtube_connection_model` — creates a `YouTubeConnection` row, verifies it persists and that `user_id` UNIQUE constraint raises `IntegrityError` on duplicate.

Add one assertion in `test_episode_with_scenes_relationship`: `assert fetched.youtube_video_id is None`.

**Step 6: Commit**

```bash
git add saas/models.py saas/schemas.py saas/youtube_auth.py requirements.txt tests/saas/test_models.py
git commit -m "feat(youtube): add YouTubeConnection model, Episode.youtube_video_id, Fernet token helpers"
```

---

## Task 2: YouTube OAuth router

**Files:**
- Create: `saas/routers/youtube.py`
- Modify: `saas/main.py`
- Create: `tests/saas/test_youtube_routes.py`

**Step 1: Write failing tests first (TDD)**

`tests/saas/test_youtube_routes.py` — cover:

1. `test_get_connect_url_returns_url` — `GET /youtube/connect` returns `{"url": "https://accounts.google.com/..."}` (mock `google_auth_oauthlib.flow.Flow.from_client_config`)
2. `test_get_status_not_connected` — returns `{"connected": false}`
3. `test_get_status_connected` — after inserting a `YouTubeConnection` row directly in DB, returns `{"connected": true, "channel_id": ..., "channel_title": ...}`
4. `test_disconnect_removes_connection` — `DELETE /youtube/disconnect` returns 204, row is gone
5. `test_disconnect_no_connection_returns_404`
6. `test_callback_creates_connection` — mock `Flow.fetch_token` + `build("youtube", ...)` channel list response; verify `YouTubeConnection` row created with encrypted token, returns `channel_id`/`channel_title`
7. `test_callback_invalid_state_returns_400` — tampered `state` JWT → 400

**Step 2: Implement `saas/routers/youtube.py`**

```python
"""YouTube OAuth connect/disconnect and status endpoints."""
from __future__ import annotations

import os
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User, YouTubeConnection
from ..schemas import YouTubeConnectOut, YouTubeStatusOut
from ..youtube_auth import decrypt_token, encrypt_token

router = APIRouter(prefix="/youtube", tags=["youtube"])

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_CLIENT_CONFIG_TEMPLATE = {
    "web": {
        "client_id": None,
        "client_secret": None,
        "redirect_uris": [None],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def _flow() -> Flow:
    cfg = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uris": [os.environ["GOOGLE_OAUTH_REDIRECT_URI"]],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(cfg, scopes=SCOPES,
        redirect_uri=os.environ["GOOGLE_OAUTH_REDIRECT_URI"])
    return flow


def _make_state(user_id: int) -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode({"user_id": user_id, "exp": time.time() + 300}, secret, algorithm="HS256")


def _verify_state(state: str) -> int:
    secret = os.environ["JWT_SECRET"]
    try:
        payload = jwt.decode(state, secret, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="ERR_INVALID_OAUTH_STATE")


@router.get("/connect", response_model=YouTubeConnectOut)
def connect(current_user: User = Depends(get_current_user)):
    flow = _flow()
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent",
        state=_make_state(current_user.id),
    )
    return YouTubeConnectOut(url=url)


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    user_id = _verify_state(state)
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    youtube = build("youtube", "v3", credentials=creds)
    ch = youtube.channels().list(part="snippet", mine=True).execute()
    channel = ch["items"][0]
    channel_id = channel["id"]
    channel_title = channel["snippet"]["title"]

    encrypted = encrypt_token(creds.refresh_token)

    existing = db.query(YouTubeConnection).filter_by(user_id=user_id).one_or_none()
    if existing:
        existing.channel_id = channel_id
        existing.channel_title = channel_title
        existing.encrypted_refresh_token = encrypted
    else:
        db.add(YouTubeConnection(
            user_id=user_id, channel_id=channel_id,
            channel_title=channel_title, encrypted_refresh_token=encrypted,
        ))
    db.commit()
    return {"channel_id": channel_id, "channel_title": channel_title}


@router.get("/status", response_model=YouTubeStatusOut)
def status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if not conn:
        return YouTubeStatusOut(connected=False)
    return YouTubeStatusOut(connected=True, channel_id=conn.channel_id, channel_title=conn.channel_title)


@router.delete("/disconnect", status_code=204)
def disconnect(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="ERR_YOUTUBE_NOT_CONNECTED")
    db.delete(conn)
    db.commit()
```

**Step 3: Register router in `saas/main.py`**

```python
from .routers.youtube import router as youtube_router
app.include_router(youtube_router)
```

**Step 4: Run tests and commit**

```bash
git add saas/routers/youtube.py saas/main.py tests/saas/test_youtube_routes.py
git commit -m "feat(youtube): add OAuth connect/callback/status/disconnect routes"
```

---

## Task 3: Upload job (Celery task + trigger route)

**Files:**
- Modify: `saas/tasks.py`
- Modify: `saas/routers/episodes.py`
- Modify: `saas/schemas.py` (if needed)
- Create: `tests/saas/test_youtube_task.py`
- Modify: `tests/saas/test_episodes_routes.py`

**Step 1: Write failing tests first (TDD)**

`tests/saas/test_youtube_task.py`:

1. `test_run_upload_succeeds` — setup: episode with `status=built`, `output_object_key` set (upload fake mp4 to moto), `YouTubeConnection` row with encrypted refresh token. Mock `google.oauth2.credentials.Credentials`, mock `googleapiclient.discovery.build` to return a fake YouTube service whose `videos().insert().execute()` returns `{"id": "abc123"}`. Call `run_upload(job_id, session_factory)`. Assert: `job.status == "done"`, `episode.status == "uploaded"`, `episode.youtube_video_id == "abc123"`.
2. `test_run_upload_marks_failed_on_api_error` — same setup, mock `videos().insert().execute()` raises `HttpError`. Assert: `job.status == "failed"`, `episode.status == "built"` (reverted).
3. `test_run_upload_fails_if_not_connected` — no `YouTubeConnection` row. Assert: `job.status == "failed"`, error message contains "not connected".

`tests/saas/test_episodes_routes.py` — add:

4. `test_trigger_upload_enqueues_job` — episode with `status=built`, `output_object_key` set, YouTube connected. Mock `upload_episode_task.delay`. `POST /episodes/{id}/upload` → 202, `{"status": "queued"}`.
5. `test_trigger_upload_requires_built_status` — episode `status=draft` → 409 `ERR_EPISODE_NOT_BUILT`.
6. `test_trigger_upload_requires_youtube_connected` — episode `status=built` but no connection → 409 `ERR_YOUTUBE_NOT_CONNECTED`.

**Step 2: Add `run_upload` to `saas/tasks.py`**

```python
from googleapiclient.discovery import build as build_youtube
from google.oauth2.credentials import Credentials as GoogleCredentials
from .models import YouTubeConnection
from .youtube_auth import decrypt_token

def run_upload(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
    job = None
    episode = None
    try:
        job = db.query(Job).filter_by(id=job_id).one()
        episode = db.query(Episode).filter_by(id=job.episode_id).one()
        job.status = "running"; episode.status = "uploading"
        db.commit()

        conn = db.query(YouTubeConnection).filter_by(user_id=episode.user_id).one_or_none()
        if conn is None:
            raise RuntimeError("YouTube not connected")

        refresh_token = decrypt_token(conn.encrypted_refresh_token)
        creds = GoogleCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            local_path = f.name
        try:
            download_to_path(episode.output_object_key, local_path)
            youtube = build_youtube("youtube", "v3", credentials=creds)
            body = {
                "snippet": {
                    "title": episode.title,
                    "description": episode.description,
                    "tags": [t.strip() for t in episode.tags.split(",") if t.strip()],
                },
                "status": {"privacyStatus": "private"},
            }
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(local_path, chunksize=-1, resumable=True)
            response = youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            ).execute()
            episode.youtube_video_id = response["id"]
        finally:
            os.unlink(local_path)

        episode.status = "uploaded"
        job.status = "done"; job.progress_pct = 100
        db.commit()

    except Exception as e:
        if job is not None:
            job.status = "failed"; job.error_message = str(e)
        if episode is not None:
            episode.status = "built"  # revert so user can retry
        db.commit()
    finally:
        db.close()


@celery_app.task(name="saas.tasks.upload_episode_task")
def upload_episode_task(job_id: int) -> None:
    run_upload(job_id, init_session_factory())
```

Note: add `"uploading"` to the allowed `Episode.status` values implicitly (no enum constraint in the model).

**Step 3: Add upload trigger route to `saas/routers/episodes.py`**

```python
@router.post("/{episode_id}/upload", status_code=202, response_model=schemas.JobOut)
def trigger_upload(
    episode_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .youtube import router as _  # noqa: ensure registered
    from ..models import YouTubeConnection
    from ..tasks import upload_episode_task

    episode = _get_owned_episode_or_404(episode_id, current_user, db)
    if episode.status != "built":
        raise HTTPException(status_code=409, detail="ERR_EPISODE_NOT_BUILT")
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if conn is None:
        raise HTTPException(status_code=409, detail="ERR_YOUTUBE_NOT_CONNECTED")

    job = Job(episode_id=episode.id, type="upload", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    upload_episode_task.delay(job.id)
    return job
```

**Step 4: Run full suite and commit**

```bash
git add saas/tasks.py saas/routers/episodes.py tests/saas/test_youtube_task.py tests/saas/test_episodes_routes.py
git commit -m "feat(youtube): add upload job task and POST /episodes/{id}/upload trigger route"
```

---

## Task 4: Env, docs, final verification

**Files:**
- Modify: `.env.example`
- Modify: `SETUP.md`
- Run full suite

**Step 1: `.env.example`**

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/youtube/callback
TOKEN_ENCRYPTION_KEY=   # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Step 2: `SETUP.md` — add YouTube section**

Brief section: how to create a Google Cloud project, enable YouTube Data API v3,
create OAuth 2.0 Web client credentials, set the 4 env vars above. Note that
`GOOGLE_OAUTH_REDIRECT_URI` must match exactly what's registered in Google Cloud Console.

**Step 3: Run full suite**

```bash
py -m pytest -q
```

Expected: all existing 154 + new tests pass.

**Step 4: Commit**

```bash
git add .env.example SETUP.md
git commit -m "docs(youtube): add Google OAuth setup instructions and env vars"
```

---

## Sequence summary

| Task | Files changed | Key deliverable |
|------|--------------|-----------------|
| 1 | models, schemas, youtube_auth.py, requirements.txt | YouTubeConnection model + Fernet helpers |
| 2 | routers/youtube.py, main.py, test_youtube_routes.py | OAuth connect/callback/status/disconnect |
| 3 | tasks.py, routers/episodes.py, test_youtube_task.py | Upload Celery task + trigger route |
| 4 | .env.example, SETUP.md | Docs + final suite verification |
