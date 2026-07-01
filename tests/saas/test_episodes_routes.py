from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import Plan, Subscription, User, YouTubeConnection
from saas.youtube_auth import encrypt_token

_FAKE_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _FAKE_ENCRYPTION_KEY)

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


def test_trigger_build_rejects_episode_with_missing_assets(client):
    headers = _signup_and_auth_headers(client, email="builder1@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": [{"narration_text": "Scene one"}]},
        headers=headers,
    ).json()

    response = client.post(f"/episodes/{created['id']}/build", headers=headers)

    assert response.status_code == 400


def test_trigger_build_rejects_when_at_plan_limit(client, db_session_factory):
    headers = _signup_and_auth_headers(client, email="builder3@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": []},
        headers=headers,
    ).json()

    session = db_session_factory()
    user = session.query(User).filter_by(email="builder3@example.com").one()
    plan = Plan(
        name="Starter",
        price_cents=1,
        currency="VND",
        billing_interval="month",
        trial_days=0,
        limits={"episodes_per_month": 1},
    )
    session.add(plan)
    session.commit()
    session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    session.commit()
    session.close()

    response = client.post(f"/episodes/{created['id']}/build", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "ERR_PLAN_LIMIT_REACHED"


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


def test_trigger_upload_enqueues_job(client, db_session_factory):
    headers = _signup_and_auth_headers(client, email="uploader@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": []},
        headers=headers,
    ).json()
    episode_id = created["id"]

    # Set episode status to built + output_object_key, and add YouTubeConnection
    session = db_session_factory()
    from saas.models import Episode as EpisodeModel
    ep = session.query(EpisodeModel).filter_by(id=episode_id).one()
    ep.status = "built"
    ep.output_object_key = "episodes/1/episode.mp4"
    user = session.query(User).filter_by(email="uploader@example.com").one()
    conn = YouTubeConnection(
        user_id=user.id,
        channel_id="UC_test",
        channel_title="Test Channel",
        encrypted_refresh_token=encrypt_token("fake-refresh-token"),
    )
    session.add(conn)
    session.commit()
    session.close()

    with patch("saas.routers.episodes.upload_episode_task") as task_mock:
        response = client.post(f"/episodes/{episode_id}/upload", headers=headers)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    task_mock.delay.assert_called_once()


def test_trigger_upload_requires_built_status(client):
    headers = _signup_and_auth_headers(client, email="uploader2@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": []},
        headers=headers,
    ).json()
    # Episode is in draft status by default

    response = client.post(f"/episodes/{created['id']}/upload", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "ERR_EPISODE_NOT_BUILT"


def test_trigger_upload_requires_youtube_connected(client, db_session_factory):
    headers = _signup_and_auth_headers(client, email="uploader3@example.com")
    created = client.post(
        "/episodes",
        json={"title": "Ep", "scenes": []},
        headers=headers,
    ).json()
    episode_id = created["id"]

    # Set episode status to built but do NOT add YouTubeConnection
    session = db_session_factory()
    from saas.models import Episode as EpisodeModel
    ep = session.query(EpisodeModel).filter_by(id=episode_id).one()
    ep.status = "built"
    ep.output_object_key = "episodes/1/episode.mp4"
    session.commit()
    session.close()

    response = client.post(f"/episodes/{episode_id}/upload", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "ERR_YOUTUBE_NOT_CONNECTED"
