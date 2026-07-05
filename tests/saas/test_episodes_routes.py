from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from moto import mock_aws

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
    url = response.json()["url"]
    assert url.startswith("https://")
    assert "whatif-test-bucket" in url


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


@mock_aws
def test_trigger_build_enqueues_job_when_all_assets_present(client, tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket

    ensure_bucket()
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
