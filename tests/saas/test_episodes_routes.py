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
