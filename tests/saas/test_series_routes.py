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


@pytest.mark.xfail(reason="episode series_id lands in task 3")
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
