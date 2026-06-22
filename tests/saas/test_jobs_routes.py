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
