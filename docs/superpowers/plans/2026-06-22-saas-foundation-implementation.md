# SaaS Foundation (DB + Auth + Episode CRUD + Build Job) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the foundational backend for the "What If" SaaS platform: PostgreSQL-backed users/episodes/scenes/jobs, JWT auth, a FastAPI REST API for episode/scene CRUD and asset upload, and a Celery job that reuses the existing video engine (`agent_video/`) to build an episode from DB rows instead of `script.md`.

**Architecture:** A new `saas/` package: SQLAlchemy models + a FastAPI app exposing `/auth`, `/episodes`, `/jobs` routers, each episode owned by a user. Building a video does not touch `agent_video/`'s code — a Celery task assembles a temporary `assets/`/`audio`/`output/` directory from DB rows (the exact shape `agent_video.image_builder`/`video_builder`/`tts` already expect) and calls those functions unchanged, then persists the resulting mp4 and updates the DB.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL (SQLite for tests), Celery + Redis, PyJWT, passlib[bcrypt], Docker Compose for local Postgres/Redis.

## Global Constraints

- Per spec, this plan covers ONLY: `users`, `episodes`, `scenes`, `jobs` tables — no `plans`/`subscriptions`/`orders`/`vouchers`/`bank_transactions`/`youtube_connections`/`site_settings`/`audit_logs` yet (those belong to later plans for billing/admin/i18n/audit).
- No third-party auth provider — self-built JWT + `users` table (spec: "Auth" decision).
- No frontend in this plan — backend/API only.
- No object storage (S3/R2/MinIO) yet — scene assets are stored on local disk under `var/uploads/`; this is an explicitly accepted interim step, not a deviation (spec's storage decision is deferred here on purpose).
- Episodes are scoped to their owning user — every episode/scene endpoint must filter by `current_user.id`, never expose another user's data.
- The video engine in `agent_video/` (`script_parser.py`, `config.py`, `tts.py`, `image_builder.py`, `video_builder.py`) is NOT modified by this plan — it is called as-is from the new Celery task.
- Existing test suite (`tests/` at repo root, 40 tests) must keep passing throughout — this plan adds a parallel `tests/saas/` tree, it does not touch `agent_video/`.

---

## File Structure

```
saas/
  __init__.py
  db.py                    # SQLAlchemy engine/session factory, Base, get_db dependency
  models.py                # User, Episode, Scene, Job ORM models
  schemas.py                # Pydantic request/response models
  security.py                # password hashing, JWT encode/decode
  deps.py                      # get_current_user dependency
  storage.py                    # local-disk asset save/read helpers
  celery_app.py                  # Celery app instance (Redis broker/backend)
  tasks.py                        # _run_build (plain function) + build_episode_task (Celery wrapper)
  routers/
    __init__.py
    auth.py                        # POST /auth/signup, POST /auth/login
    episodes.py                     # episode/scene CRUD, asset upload, build trigger
    jobs.py                           # GET /jobs/{id}
  main.py                             # FastAPI app wiring all routers
docker-compose.yml             # postgres + redis for local dev
tests/saas/
  conftest.py                        # SQLite test DB, FastAPI TestClient fixture, auth helper
  test_security.py
  test_auth_routes.py
  test_episodes_routes.py
  test_storage.py
  test_tasks.py
  test_jobs_routes.py
```

---

### Task 1: Project scaffolding — dependencies, Docker Compose, DB session

**Files:**
- Modify: `requirements.txt` (append new deps)
- Create: `docker-compose.yml`
- Create: `.env.example` additions (append, don't replace existing ElevenLabs lines)
- Create: `saas/__init__.py`
- Create: `saas/db.py`
- Create: `tests/saas/__init__.py`
- Create: `tests/saas/conftest.py`

**Interfaces:**
- Produces: `saas.db.Base` (SQLAlchemy declarative base), `saas.db.get_db_session_factory(database_url: str) -> sessionmaker`, `saas.db.get_db() -> Generator[Session, None, None]` (FastAPI dependency, uses a module-level `SessionLocal` configured from `DATABASE_URL` env var). Task 2 (`models.py`) defines tables against `Base`. Tests override `get_db` to point at an in-memory SQLite session instead of Postgres.

- [ ] **Step 1: Add new dependencies**

Append to `D:/Video/agent_video/requirements.txt`:
```
fastapi>=0.111.0
uvicorn>=0.30.0
sqlalchemy>=2.0.30
psycopg2-binary>=2.9.9
PyJWT>=2.8.0
passlib[bcrypt]>=1.7.4
celery>=5.4.0
redis>=5.0.0
python-multipart>=0.0.9
httpx>=0.27.0
```

- [ ] **Step 2: Install dependencies**

Run: `py -m pip install -r requirements.txt`
Expected: all packages install without error (note: `psycopg2-binary` requires no real Postgres running yet — it's just the driver).

- [ ] **Step 3: Create `docker-compose.yml`**

Create `D:/Video/agent_video/docker-compose.yml`:
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: whatif
      POSTGRES_PASSWORD: whatif
      POSTGRES_DB: whatif
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

- [ ] **Step 4: Document new env vars**

Append to `D:/Video/agent_video/.env.example` (keep existing `ELEVENLABS_*` lines above):
```
DATABASE_URL=postgresql+psycopg2://whatif:whatif@localhost:5432/whatif
JWT_SECRET=change-me-to-a-long-random-string
REDIS_URL=redis://localhost:6379/0
```

- [ ] **Step 5: Create the `saas` package and `db.py`**

Create `D:/Video/agent_video/saas/__init__.py` (empty file).

Create `D:/Video/agent_video/saas/db.py`:
```python
"""SQLAlchemy engine/session setup."""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def get_db_session_factory(database_url: str) -> sessionmaker:
    engine = create_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


_SessionLocal: sessionmaker | None = None


def init_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        database_url = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg2://whatif:whatif@localhost:5432/whatif"
        )
        _SessionLocal = get_db_session_factory(database_url)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session_factory = init_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Create the shared test fixtures**

Create `D:/Video/agent_video/tests/saas/__init__.py` (empty file).

Create `D:/Video/agent_video/tests/saas/conftest.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from saas.db import Base


@pytest.fixture
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()
```

- [ ] **Step 7: Verify the package imports cleanly**

Run: `py -c "from saas.db import Base, get_db_session_factory; print('ok')"`
Expected: prints `ok` (no models exist yet, so `Base.metadata` is empty — that's expected at this step).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt docker-compose.yml .env.example saas/__init__.py saas/db.py tests/saas/__init__.py tests/saas/conftest.py
git commit -m "chore: scaffold saas package, DB session factory, Docker Compose"
```

---

### Task 2: ORM models — User, Episode, Scene, Job

**Files:**
- Create: `saas/models.py`
- Create: `tests/saas/test_models.py`

**Interfaces:**
- Consumes: `saas.db.Base` (Task 1).
- Produces: `saas.models.User(id, email, password_hash, role, created_at)`, `saas.models.Episode(id, user_id, title, description, tags, status, output_path, created_at)` with `.scenes` relationship, `saas.models.Scene(id, episode_id, order_index, narration_text, asset_path, created_at)`, `saas.models.Job(id, episode_id, type, status, progress_pct, error_message, created_at)`. Every later task imports these exact class/column names.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_models.py`:
```python
from saas.models import Episode, Job, Scene, User


def test_create_user(db_session):
    user = User(email="a@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter_by(email="a@example.com").one()
    assert fetched.role == "user"
    assert fetched.created_at is not None


def test_episode_with_scenes_relationship(db_session):
    user = User(email="b@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(
        user_id=user.id,
        title="What If The Moon Disappeared",
        description="desc",
        tags="whatif,space",
        status="draft",
    )
    episode.scenes.append(Scene(order_index=0, narration_text="Scene one text"))
    episode.scenes.append(Scene(order_index=1, narration_text="Scene two text"))
    db_session.add(episode)
    db_session.commit()

    fetched = db_session.query(Episode).filter_by(title="What If The Moon Disappeared").one()
    assert fetched.status == "draft"
    assert fetched.output_path is None
    assert len(fetched.scenes) == 2
    assert fetched.scenes[0].narration_text == "Scene one text"
    assert fetched.scenes[0].asset_path is None


def test_job_defaults(db_session):
    user = User(email="c@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()
    episode = Episode(user_id=user.id, title="T", description="", tags="", status="draft")
    db_session.add(episode)
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    fetched = db_session.query(Job).filter_by(episode_id=episode.id).one()
    assert fetched.progress_pct == 0
    assert fetched.error_message is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.models'`.

- [ ] **Step 3: Implement `saas/models.py`**

Create `D:/Video/agent_video/saas/models.py`:
```python
"""SQLAlchemy ORM models for the SaaS foundation: users, episodes, scenes, jobs."""
from __future__ import annotations

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="episode", order_by="Scene.order_index", cascade="all, delete-orphan"
    )


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    narration_text: Mapped[str] = mapped_column(Text, nullable=False)
    asset_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())

    episode: Mapped["Episode"] = relationship(back_populates="scenes")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_models.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add saas/models.py tests/saas/test_models.py
git commit -m "feat: add User/Episode/Scene/Job ORM models"
```

---

### Task 3: Password hashing + JWT (`saas/security.py`)

**Files:**
- Create: `saas/security.py`
- Create: `tests/saas/test_security.py`

**Interfaces:**
- Produces: `saas.security.hash_password(password: str) -> str`, `saas.security.verify_password(password: str, password_hash: str) -> bool`, `saas.security.create_access_token(user_id: int, secret: str, expires_minutes: int = 60 * 24) -> str`, `saas.security.decode_access_token(token: str, secret: str) -> int` (returns `user_id`, raises `saas.security.InvalidTokenError` on failure). Task 5 (`routers/auth.py`) and Task 4 (`deps.py`) use these exact names.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_security.py`:
```python
import time

import pytest

from saas.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    password_hash = hash_password("correct-password")
    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_hash_password_does_not_store_plaintext():
    password_hash = hash_password("secret123")
    assert "secret123" not in password_hash


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42, secret="test-secret")
    user_id = decode_access_token(token, secret="test-secret")
    assert user_id == 42


def test_decode_access_token_rejects_wrong_secret():
    token = create_access_token(user_id=42, secret="test-secret")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="different-secret")


def test_decode_access_token_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-real-token", secret="test-secret")


def test_create_access_token_respects_expiry():
    token = create_access_token(user_id=1, secret="s", expires_minutes=-1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="s")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.security'`.

- [ ] **Step 3: Implement `saas/security.py`**

Create `D:/Video/agent_video/saas/security.py`:
```python
"""Password hashing and JWT access tokens."""
from __future__ import annotations

import datetime

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, secret: str, expires_minutes: int = 60 * 24) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + datetime.timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> int:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return int(payload["sub"])
    except jwt.PyJWTError as e:
        raise InvalidTokenError(str(e)) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_security.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add saas/security.py tests/saas/test_security.py
git commit -m "feat: add password hashing and JWT access tokens"
```

---

### Task 4: Pydantic schemas + `get_current_user` dependency

**Files:**
- Create: `saas/schemas.py`
- Create: `saas/deps.py`
- Create: `tests/saas/test_deps.py`

**Interfaces:**
- Consumes: `saas.models.User` (Task 2), `saas.security.decode_access_token`/`InvalidTokenError` (Task 3), `saas.db.get_db` (Task 1).
- Produces: `saas.schemas.SignupRequest(email: str, password: str)`, `saas.schemas.LoginRequest(email: str, password: str)`, `saas.schemas.TokenResponse(access_token: str, token_type: str = "bearer")`, `saas.schemas.SceneIn(narration_text: str)`, `saas.schemas.SceneOut(id: int, order_index: int, narration_text: str, asset_path: str | None)`, `saas.schemas.EpisodeIn(title: str, description: str = "", tags: str = "", scenes: list[SceneIn])`, `saas.schemas.EpisodeOut(id, title, description, tags, status, output_path, scenes: list[SceneOut])`, `saas.schemas.JobOut(id, status, progress_pct, error_message)`. Produces `saas.deps.get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User` (FastAPI dependency, raises `HTTPException(401)` on missing/invalid token or unknown user). Tasks 5/6 (routers) depend on these exact names.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_deps.py`:
```python
import pytest
from fastapi import HTTPException

from saas.deps import get_current_user
from saas.models import User
from saas.security import create_access_token, hash_password

JWT_SECRET = "test-secret"


def test_get_current_user_returns_user_for_valid_token(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = User(email="x@example.com", password_hash=hash_password("pw"), role="user")
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, secret=JWT_SECRET)

    result = get_current_user(authorization=f"Bearer {token}", db=db_session)

    assert result.id == user.id
    assert result.email == "x@example.com"


def test_get_current_user_rejects_missing_header(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None, db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer garbage", db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_unknown_user_id(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = create_access_token(user_id=99999, secret=JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", db=db_session)
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.deps'`.

- [ ] **Step 3: Implement `saas/schemas.py`**

Create `D:/Video/agent_video/saas/schemas.py`:
```python
"""Pydantic request/response models for the SaaS API."""
from __future__ import annotations

from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SceneIn(BaseModel):
    narration_text: str


class SceneOut(BaseModel):
    id: int
    order_index: int
    narration_text: str
    asset_path: str | None

    class Config:
        from_attributes = True


class EpisodeIn(BaseModel):
    title: str
    description: str = ""
    tags: str = ""
    scenes: list[SceneIn] = []


class EpisodeOut(BaseModel):
    id: int
    title: str
    description: str
    tags: str
    status: str
    output_path: str | None
    scenes: list[SceneOut]

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: int
    status: str
    progress_pct: int
    error_message: str | None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Implement `saas/deps.py`**

Create `D:/Video/agent_video/saas/deps.py`:
```python
"""FastAPI dependencies: current authenticated user."""
from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import InvalidTokenError, decode_access_token


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    secret = os.environ["JWT_SECRET"]

    try:
        user_id = decode_access_token(token, secret)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_deps.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add saas/schemas.py saas/deps.py tests/saas/test_deps.py
git commit -m "feat: add Pydantic schemas and get_current_user dependency"
```

---

### Task 5: Auth routes — signup/login

**Files:**
- Create: `saas/routers/__init__.py`
- Create: `saas/routers/auth.py`
- Create: `saas/main.py`
- Create: `tests/saas/test_auth_routes.py`

**Interfaces:**
- Consumes: `saas.models.User` (Task 2), `saas.security.hash_password/verify_password/create_access_token` (Task 3), `saas.schemas.SignupRequest/LoginRequest/TokenResponse` (Task 4), `saas.db.get_db` (Task 1).
- Produces: `saas.routers.auth.router` (FastAPI `APIRouter`, mounted at `/auth`), `saas.main.app` (the FastAPI app — Task 6/7 add more routers to it, Task 9 needs `app` for `TestClient`).

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_auth_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

from saas.db import Base, get_db
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


def test_signup_creates_user_and_returns_token(client):
    response = client.post("/auth/signup", json={"email": "new@example.com", "password": "pw12345"})

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_signup_rejects_duplicate_email(client):
    client.post("/auth/signup", json={"email": "dup@example.com", "password": "pw12345"})
    response = client.post("/auth/signup", json={"email": "dup@example.com", "password": "other"})

    assert response.status_code == 400


def test_login_returns_token_for_correct_credentials(client):
    client.post("/auth/signup", json={"email": "login@example.com", "password": "correct-pw"})

    response = client.post("/auth/login", json={"email": "login@example.com", "password": "correct-pw"})

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_rejects_wrong_password(client):
    client.post("/auth/signup", json={"email": "login2@example.com", "password": "correct-pw"})

    response = client.post("/auth/login", json={"email": "login2@example.com", "password": "wrong-pw"})

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": "x"})

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_auth_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.main'`.

- [ ] **Step 3: Implement `saas/routers/auth.py`**

Create `D:/Video/agent_video/saas/routers/__init__.py` (empty file).

Create `D:/Video/agent_video/saas/routers/auth.py`:
```python
"""Signup and login routes."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import LoginRequest, SignupRequest, TokenResponse
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(User).filter_by(email=payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()

    token = create_access_token(user.id, secret=os.environ["JWT_SECRET"])
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter_by(email=payload.email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.id, secret=os.environ["JWT_SECRET"])
    return TokenResponse(access_token=token)
```

- [ ] **Step 4: Implement `saas/main.py`**

Create `D:/Video/agent_video/saas/main.py`:
```python
"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .routers import auth

app = FastAPI(title="What If API")
app.include_router(auth.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_auth_routes.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add saas/routers/__init__.py saas/routers/auth.py saas/main.py tests/saas/test_auth_routes.py
git commit -m "feat: add signup/login routes and FastAPI app entry point"
```

---

### Task 6: Episode + scene CRUD routes

**Files:**
- Create: `saas/routers/episodes.py`
- Modify: `saas/main.py` (register the new router)
- Create: `tests/saas/test_episodes_routes.py`

**Interfaces:**
- Consumes: `saas.models.Episode/Scene` (Task 2), `saas.schemas.EpisodeIn/EpisodeOut` (Task 4), `saas.deps.get_current_user` (Task 4), `saas.db.get_db` (Task 1).
- Produces: `saas.routers.episodes.router` mounted at `/episodes`: `POST /episodes` (create with nested scenes), `GET /episodes` (list current user's own episodes), `GET /episodes/{episode_id}` (404 if not found or not owned by current user). Task 7 (asset upload, build trigger) adds more routes to this same router/file.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_episodes_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient

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


def _signup_and_auth_headers(client, email="owner@example.com"):
    response = client.post("/auth/signup", json={"email": email, "password": "pw12345"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_episode_with_scenes(client):
    headers = _signup_and_auth_headers(client)

    response = client.post(
        "/episodes",
        json={
            "title": "What If The Moon Disappeared",
            "description": "desc",
            "tags": "whatif,space",
            "scenes": [{"narration_text": "Scene one"}, {"narration_text": "Scene two"}],
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "What If The Moon Disappeared"
    assert body["status"] == "draft"
    assert len(body["scenes"]) == 2
    assert body["scenes"][0]["order_index"] == 0
    assert body["scenes"][1]["order_index"] == 1


def test_list_episodes_only_returns_own_episodes(client):
    headers_a = _signup_and_auth_headers(client, email="a@example.com")
    headers_b = _signup_and_auth_headers(client, email="b@example.com")
    client.post("/episodes", json={"title": "A's episode", "scenes": []}, headers=headers_a)
    client.post("/episodes", json={"title": "B's episode", "scenes": []}, headers=headers_b)

    response = client.get("/episodes", headers=headers_a)

    assert response.status_code == 200
    titles = [ep["title"] for ep in response.json()]
    assert titles == ["A's episode"]


def test_get_episode_returns_404_for_other_users_episode(client):
    headers_a = _signup_and_auth_headers(client, email="c@example.com")
    headers_b = _signup_and_auth_headers(client, email="d@example.com")
    created = client.post("/episodes", json={"title": "C's episode", "scenes": []}, headers=headers_a).json()

    response = client.get(f"/episodes/{created['id']}", headers=headers_b)

    assert response.status_code == 404


def test_create_episode_requires_auth(client):
    response = client.post("/episodes", json={"title": "No auth", "scenes": []})

    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_episodes_routes.py -v`
Expected: FAIL with `404 Not Found` for `/episodes` (router not yet registered) or an import error, depending on test order — confirm the failure is because the route doesn't exist yet, not a typo in the test.

- [ ] **Step 3: Implement `saas/routers/episodes.py`**

Create `D:/Video/agent_video/saas/routers/episodes.py`:
```python
"""Episode and scene CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Scene, User
from ..schemas import EpisodeIn, EpisodeOut

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=EpisodeOut, status_code=201)
def create_episode(
    payload: EpisodeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
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
```

- [ ] **Step 4: Register the router in `saas/main.py`**

Edit `D:/Video/agent_video/saas/main.py`:
```python
"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .routers import auth, episodes

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(episodes.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_episodes_routes.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add saas/routers/episodes.py saas/main.py tests/saas/test_episodes_routes.py
git commit -m "feat: add episode/scene CRUD routes scoped to current user"
```

---

### Task 7: Local asset storage + upload route

**Files:**
- Create: `saas/storage.py`
- Modify: `saas/routers/episodes.py` (add upload route)
- Create: `tests/saas/test_storage.py`
- Modify: `tests/saas/test_episodes_routes.py` (add upload test)

**Interfaces:**
- Produces: `saas.storage.save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str` (returns a relative path like `episodes/3/scenes/7.png`, creating parent dirs under `var/uploads/` as needed), `saas.storage.get_asset_abs_path(relative_path: str) -> str` (resolves a relative path back to an absolute filesystem path under `var/uploads/`). Task 9 (`tasks.py`) uses `get_asset_abs_path` to read uploaded files when building a video.
- Adds route: `POST /episodes/{episode_id}/scenes/{scene_id}/asset` (multipart file upload), sets `Scene.asset_path`.

- [ ] **Step 1: Write failing tests for storage**

Create `D:/Video/agent_video/tests/saas/test_storage.py`:
```python
import os

from saas.storage import get_asset_abs_path, save_asset


def test_save_asset_writes_file_and_returns_relative_path(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))

    relative_path = save_asset(episode_id=3, scene_id=7, filename="hero.png", content=b"fake-png-bytes")

    assert relative_path == os.path.join("episodes", "3", "scenes", "7.png")
    abs_path = get_asset_abs_path(relative_path)
    with open(abs_path, "rb") as f:
        assert f.read() == b"fake-png-bytes"


def test_save_asset_preserves_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))

    relative_path = save_asset(episode_id=1, scene_id=2, filename="photo.jpeg", content=b"x")

    assert relative_path.endswith(".jpeg")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.storage'`.

- [ ] **Step 3: Implement `saas/storage.py`**

Create `D:/Video/agent_video/saas/storage.py`:
```python
"""Local-disk storage for user-uploaded scene assets (interim, pre-object-storage)."""
from __future__ import annotations

import os


def _uploads_root() -> str:
    return os.environ.get("UPLOADS_DIR", os.path.join("var", "uploads"))


def save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    relative_path = os.path.join("episodes", str(episode_id), "scenes", f"{scene_id}{ext}")
    abs_path = os.path.join(_uploads_root(), relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(content)
    return relative_path


def get_asset_abs_path(relative_path: str) -> str:
    return os.path.join(_uploads_root(), relative_path)
```

- [ ] **Step 4: Run storage tests to verify they pass**

Run: `py -m pytest tests/saas/test_storage.py -v`
Expected: Both tests PASS.

- [ ] **Step 5: Write the failing test for the upload route**

Append to `D:/Video/agent_video/tests/saas/test_episodes_routes.py` (add this function at the end of the file):
```python
def test_upload_scene_asset_sets_asset_path(client, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
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
    assert response.json()["asset_path"].endswith(".png")

    refetched = client.get(f"/episodes/{created['id']}", headers=headers).json()
    assert refetched["scenes"][0]["asset_path"] == response.json()["asset_path"]
```

- [ ] **Step 6: Run the new test to verify it fails**

Run: `py -m pytest tests/saas/test_episodes_routes.py::test_upload_scene_asset_sets_asset_path -v`
Expected: FAIL with `404 Not Found` (route doesn't exist yet).

- [ ] **Step 7: Add the upload route to `saas/routers/episodes.py`**

Append to `D:/Video/agent_video/saas/routers/episodes.py` (add these imports to the top and the route at the bottom):
```python
from fastapi import File, UploadFile

from ..schemas import SceneOut
from ..storage import save_asset


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
    relative_path = save_asset(episode_id, scene_id, file.filename, content)
    scene.asset_path = relative_path
    db.commit()
    return scene
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_episodes_routes.py tests/saas/test_storage.py -v`
Expected: All tests PASS (5 in test_episodes_routes.py, 2 in test_storage.py).

- [ ] **Step 9: Commit**

```bash
git add saas/storage.py saas/routers/episodes.py tests/saas/test_storage.py tests/saas/test_episodes_routes.py
git commit -m "feat: add local asset storage and scene asset upload route"
```

---

### Task 8: Celery app + build task (reuses the video engine)

**Files:**
- Create: `saas/celery_app.py`
- Create: `saas/tasks.py`
- Create: `tests/saas/test_tasks.py`

**Interfaces:**
- Consumes: `saas.models.Episode/Scene/Job` (Task 2), `saas.storage.get_asset_abs_path` (Task 7), `saas.db` session factory pattern (Task 1), and from the existing engine: `agent_video.script_parser.Episode` / `Scene` (dataclasses, NOT the SQLAlchemy models — same names, different module, the task must alias one import), `agent_video.config.DEFAULT_CONFIG`, `agent_video.tts.synthesize_scene`/`get_audio_duration`, `agent_video.image_builder.build_scene_clip`, `agent_video.video_builder.build_episode`.
- Produces: `saas.tasks.run_build(job_id: int, session_factory: sessionmaker) -> None` (the plain, directly-testable function — does the actual work), `saas.celery_app.celery_app` (Celery instance), `saas.tasks.build_episode_task` (the `@celery_app.task`-wrapped Celery entry point that calls `run_build(job_id, saas.db.init_session_factory())`). Task 9 (`routers/jobs.py` and the build-trigger route added to `episodes.py`) calls `build_episode_task.delay(job_id)`.

- [ ] **Step 1: Write failing tests**

Create `D:/Video/agent_video/tests/saas/test_tasks.py`:
```python
import os
from unittest.mock import MagicMock, patch

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _make_episode_with_one_scene(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("EPISODES_DIR", str(tmp_path / "episodes"))

    user = User(email="e@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Test Episode", description="", tags="", status="ready")
    scene = Scene(order_index=0, narration_text="Hello world", asset_path=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    asset_dir = tmp_path / "uploads" / "episodes" / str(episode.id) / "scenes"
    asset_dir.mkdir(parents=True)
    (asset_dir / f"{scene.id}.png").write_bytes(b"fake-png-bytes")
    scene.asset_path = os.path.join("episodes", str(episode.id), "scenes", f"{scene.id}.png")
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    return episode.id, job.id


def test_run_build_succeeds_and_updates_episode_and_job(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, tmp_path, monkeypatch)

    with patch("saas.tasks.synthesize_scene") as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip") as clip_mock, \
         patch("saas.tasks.build_episode", return_value="/fake/output/episode.mp4") as build_ep_mock:
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
    assert episode.output_path is not None
    fresh.close()


def test_run_build_marks_job_failed_on_exception(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, tmp_path, monkeypatch)

    with patch("saas.tasks.synthesize_scene", side_effect=RuntimeError("ElevenLabs exploded")):
        run_build(job_id, db_session_factory)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "failed"
    assert "ElevenLabs exploded" in job.error_message
    assert episode.status == "ready"
    fresh.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.tasks'`.

- [ ] **Step 3: Implement `saas/celery_app.py`**

Create `D:/Video/agent_video/saas/celery_app.py`:
```python
"""Celery app instance, Redis broker/backend."""
from __future__ import annotations

import os

from celery import Celery

celery_app = Celery(
    "saas",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)
```

- [ ] **Step 4: Implement `saas/tasks.py`**

Create `D:/Video/agent_video/saas/tasks.py`:
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
from .storage import get_asset_abs_path


def _episodes_dir() -> str:
    return os.environ.get("EPISODES_DIR", os.path.join("var", "episodes"))


def run_build(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
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

            engine_scenes = []
            for scene in episode.scenes:
                scene_name = f"scene_{scene.order_index:02d}"
                engine_scenes.append(
                    EngineScene(name=scene_name, asset=get_asset_abs_path(scene.asset_path), text=scene.narration_text)
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

            final_dir = os.path.join(_episodes_dir(), str(episode.id))
            os.makedirs(final_dir, exist_ok=True)
            final_path = os.path.join(final_dir, "episode.mp4")
            shutil.copyfile(out_path, final_path)

            episode.output_path = final_path
            episode.status = "built"
            job.status = "done"
            job.progress_pct = 100
            db.commit()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        episode.status = "ready"
        db.commit()
    finally:
        db.close()


@celery_app.task(name="saas.tasks.build_episode_task")
def build_episode_task(job_id: int) -> None:
    run_build(job_id, init_session_factory())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest tests/saas/test_tasks.py -v`
Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add saas/celery_app.py saas/tasks.py tests/saas/test_tasks.py
git commit -m "feat: add Celery build task that reuses the existing video engine"
```

---

### Task 9: Build-trigger route + Jobs route

**Files:**
- Modify: `saas/routers/episodes.py` (add `POST /episodes/{episode_id}/build`)
- Create: `saas/routers/jobs.py`
- Modify: `saas/main.py` (register jobs router)
- Modify: `tests/saas/test_episodes_routes.py` (add build-trigger test)
- Create: `tests/saas/test_jobs_routes.py`

**Interfaces:**
- Consumes: `saas.tasks.build_episode_task` (Task 8), `saas.models.Job` (Task 2), `saas.schemas.JobOut` (Task 4).
- Produces: `POST /episodes/{episode_id}/build` → creates a `Job(type="build", status="queued")`, enqueues `build_episode_task.delay(job.id)`, returns `JobOut`; rejects with 400 if any scene has `asset_path is None`. `GET /jobs/{job_id}` → returns `JobOut`, scoped to jobs belonging to the current user's own episodes (404 otherwise).

- [ ] **Step 1: Write failing tests for the build-trigger route**

Append to `D:/Video/agent_video/tests/saas/test_episodes_routes.py`:
```python
from unittest.mock import patch


def test_trigger_build_rejects_episode_with_missing_assets(client):
    headers = _signup_and_auth_headers(client, email="builder1@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]},
        headers=headers,
    ).json()

    response = client.post(f"/episodes/{created['id']}/build", headers=headers)

    assert response.status_code == 400


def test_trigger_build_enqueues_job_when_all_assets_present(client, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    headers = _signup_and_auth_headers(client, email="builder2@example.com")
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

    with patch("saas.routers.episodes.build_episode_task") as task_mock:
        response = client.post(f"/episodes/{created['id']}/build", headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    task_mock.delay.assert_called_once()
```

- [ ] **Step 2: Write failing tests for the jobs route**

Create `D:/Video/agent_video/tests/saas/test_jobs_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

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


def _signup_and_auth_headers(client, email):
    response = client.post("/auth/signup", json={"email": email, "password": "pw12345"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_job_returns_status_for_own_episode(client, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    headers = _signup_and_auth_headers(client, "jobowner@example.com")
    created = client.post(
        "/episodes", json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]}, headers=headers
    ).json()
    scene_id = created["scenes"][0]["id"]
    client.post(
        f"/episodes/{created['id']}/scenes/{scene_id}/asset",
        files={"file": ("hero.png", b"fake-bytes", "image/png")},
        headers=headers,
    )
    with patch("saas.routers.episodes.build_episode_task"):
        job = client.post(f"/episodes/{created['id']}/build", headers=headers).json()

    response = client.get(f"/jobs/{job['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_get_job_returns_404_for_other_users_job(client, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    headers_a = _signup_and_auth_headers(client, "joba@example.com")
    headers_b = _signup_and_auth_headers(client, "jobb@example.com")
    created = client.post(
        "/episodes", json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]}, headers=headers_a
    ).json()
    scene_id = created["scenes"][0]["id"]
    client.post(
        f"/episodes/{created['id']}/scenes/{scene_id}/asset",
        files={"file": ("hero.png", b"fake-bytes", "image/png")},
        headers=headers_a,
    )
    with patch("saas.routers.episodes.build_episode_task"):
        job = client.post(f"/episodes/{created['id']}/build", headers=headers_a).json()

    response = client.get(f"/jobs/{job['id']}", headers=headers_b)

    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -m pytest tests/saas/test_episodes_routes.py tests/saas/test_jobs_routes.py -v`
Expected: FAIL — the build/job tests error because the build-trigger route and `/jobs` router don't exist yet.

- [ ] **Step 4: Add the build-trigger route to `saas/routers/episodes.py`**

Append to `D:/Video/agent_video/saas/routers/episodes.py` (add these imports to the top and the route at the bottom):
```python
from ..models import Job
from ..schemas import JobOut
from ..tasks import build_episode_task


@router.post("/{episode_id}/build", response_model=JobOut, status_code=202)
def trigger_build(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if any(scene.asset_path is None for scene in episode.scenes):
        raise HTTPException(status_code=400, detail="All scenes must have an uploaded asset before building")

    job = Job(episode_id=episode.id, type="build", status="queued")
    db.add(job)
    db.commit()

    build_episode_task.delay(job.id)
    return job
```

- [ ] **Step 5: Implement `saas/routers/jobs.py`**

Create `D:/Video/agent_video/saas/routers/jobs.py`:
```python
"""Job status route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Job, User
from ..schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Job:
    job = (
        db.query(Job)
        .join(Episode, Episode.id == Job.episode_id)
        .filter(Job.id == job_id, Episode.user_id == current_user.id)
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

- [ ] **Step 6: Register the jobs router in `saas/main.py`**

Edit `D:/Video/agent_video/saas/main.py`:
```python
"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .routers import auth, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `py -m pytest tests/saas/ -v`
Expected: All tests in the `tests/saas/` tree PASS.

- [ ] **Step 8: Run the full repo test suite to confirm no regressions**

Run: `py -m pytest -q`
Expected: All tests pass (the pre-existing 40 `agent_video` tests plus the new `saas` tests).

- [ ] **Step 9: Commit**

```bash
git add saas/routers/episodes.py saas/routers/jobs.py saas/main.py tests/saas/test_episodes_routes.py tests/saas/test_jobs_routes.py
git commit -m "feat: add build-trigger and job status routes"
```

---

### Task 10: SETUP.md update + manual verification

**Files:**
- Modify: `SETUP.md` (append a new section)

**Interfaces:** none (documentation + manual verification).

- [ ] **Step 1: Append a SaaS foundation setup section to `SETUP.md`**

Append to `D:/Video/agent_video/SETUP.md`:
```markdown

## 5. SaaS foundation (API + DB + background jobs)

1. Start Postgres and Redis: `docker compose up -d`
2. Copy the new variables from `.env.example` into `.env`: `DATABASE_URL`, `JWT_SECRET` (use a long random string), `REDIS_URL`.
3. Create the database tables (one-time, until a real migration tool is introduced):
   ```
   py -c "from saas.db import Base, init_session_factory; Base.metadata.create_all(init_session_factory().kw['bind'])"
   ```
4. Start the API: `py -m uvicorn saas.main:app --reload`
5. Start a Celery worker (separate terminal): `py -m celery -A saas.celery_app.celery_app worker --loglevel=info --pool=solo`
6. Open http://127.0.0.1:8000/docs for interactive API docs (signup, create an episode, upload assets per scene, trigger a build, poll `/jobs/{id}`).
```

- [ ] **Step 2: Commit**

```bash
git add SETUP.md
git commit -m "docs: add SaaS foundation setup instructions"
```

- [ ] **Step 3: Manual verification (requires Docker running and real ElevenLabs credentials for a full build; the API/DB/auth/CRUD layer can be verified without them)**

With `docker compose up -d` running and the DB tables created (Step 1 above):
```
py -m uvicorn saas.main:app
```
In a second terminal:
```
curl -X POST http://127.0.0.1:8000/auth/signup -H "Content-Type: application/json" -d "{\"email\":\"me@example.com\",\"password\":\"pw12345\"}"
```
Expected: a JSON response containing `access_token`. Use that token as `Authorization: Bearer <token>` to `POST /episodes`, then `POST /episodes/{id}/scenes/{scene_id}/asset` (multipart file), then `POST /episodes/{id}/build` (requires a running Celery worker and real `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` in `.env` to actually complete — without them, confirm the job ends with `status: "failed"` and an `error_message` mentioning the missing credentials, mirroring the actionable-error behavior already verified in the CLI engine).

## Self-Review Notes

- **Spec coverage:** users/episodes/scenes/jobs tables (Task 2), JWT auth without third-party provider (Task 3/5), episode/scene CRUD via REST scoped per-user (Task 6), asset upload replacing manual `assets/` folder drops (Task 7), Celery job queue reusing the existing engine unchanged (Task 8), build-trigger + job polling (Task 9). Explicitly deferred per Global Constraints: billing, admin, i18n, audit log, object storage, frontend — each is its own future plan.
- **Placeholder scan:** no TBD/TODO; every step has runnable code.
- **Type consistency:** `Episode`/`Scene` names collide between `saas.models` (SQLAlchemy ORM) and `agent_video.script_parser` (plain dataclasses) — Task 8 resolves this with explicit `as` imports (`EngineEpisode`, `EngineScene`) to avoid ambiguity; later tasks importing `saas.tasks.build_episode_task` are unaffected by this internal aliasing. `run_build(job_id, session_factory)` signature defined in Task 8 is used identically by both its tests and `build_episode_task` in the same file.
