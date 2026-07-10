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


def test_gpt_image_provider_raises_on_malformed_base64(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        ip.requests,
        "post",
        lambda *a, **k: FakeHttpResponse(200, {"data": [{"b64_json": "!!!not-base64!!!"}]}),
    )
    with pytest.raises(ImageError):
        GptImageProvider().generate("x")


def test_gpt_image_provider_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        ip.requests, "post", lambda *a, **k: FakeHttpResponse(400, {"error": "bad"})
    )
    with pytest.raises(ImageError):
        GptImageProvider().generate("x")


def test_gpt_image_provider_catches_connection_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fake_post_fails(*a, **k):
        raise ip.requests.ConnectionError("boom")

    monkeypatch.setattr(ip.requests, "post", fake_post_fails)
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
