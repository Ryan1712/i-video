import pytest
from fastapi.testclient import TestClient

import saas.ai.script_generation as sg
import saas.routers.episodes as episodes_router
from saas.ai.client import AIError
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


def test_word_target_scales_with_duration_and_language():
    assert sg._target_words(480, "en") == 480 // 60 * 150
    assert sg._target_words(480, "vi") == 480 // 60 * 160


def test_generate_script_builds_prompt_and_returns_text(monkeypatch):
    captured = {}

    def fake_generate_json(system, user_message, max_tokens=8192):
        captured["system"] = system
        captured["user"] = user_message
        return {"script": "Once upon a time..."}

    monkeypatch.setattr(sg, "generate_json", fake_generate_json)
    script = sg.generate_script("zombies attack", 480, "en", "What If", "zombie series")
    assert script == "Once upon a time..."
    assert "zombies attack" in captured["user"]
    assert "1200 words" in captured["user"]  # 8 min * 150 wpm
    assert "English" in captured["system"]


def test_generate_script_rejects_missing_script_key(monkeypatch):
    monkeypatch.setattr(sg, "generate_json", lambda *a, **k: {"wrong": 1})
    with pytest.raises(AIError):
        sg.generate_script("b", 60, "en")


def test_endpoint_stores_fields_and_returns_script(client, monkeypatch):
    monkeypatch.setattr(
        episodes_router, "generate_script", lambda **kwargs: "Generated script."
    )
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "zombie outbreak", "target_duration_sec": 480},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["script"] == "Generated script."

    ep = client.get(f"/episodes/{ep_id}", headers=headers).json()
    assert ep["brief"] == "zombie outbreak"
    assert ep["target_duration_sec"] == 480
    assert ep["script"] == "Generated script."


def test_endpoint_maps_aierror_to_502(client, monkeypatch):
    def boom(**kwargs):
        raise AIError("bad json")

    monkeypatch.setattr(episodes_router, "generate_script", boom)
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "b", "target_duration_sec": 60},
        headers=headers,
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "ERR_SCRIPT_GENERATION_FAILED"


def test_endpoint_conflicts_when_not_draft(client, monkeypatch):
    monkeypatch.setattr(episodes_router, "generate_script", lambda **kwargs: "x")
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers).json()["id"]

    from saas.models import Episode
    db = client.app.dependency_overrides[get_db]().__next__()
    db.query(Episode).filter_by(id=ep_id).update({"status": "built"})
    db.commit()

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "b", "target_duration_sec": 60},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ERR_EPISODE_NOT_DRAFT"


def test_endpoint_is_owner_scoped(client, monkeypatch):
    monkeypatch.setattr(episodes_router, "generate_script", lambda **kwargs: "x")
    headers_a = _auth(client, "a@example.com")
    headers_b = _auth(client, "b@example.com")
    ep_id = client.post("/episodes", json={"title": "EP1", "scenes": []}, headers=headers_a).json()["id"]

    resp = client.post(
        f"/episodes/{ep_id}/generate-script",
        json={"brief": "b", "target_duration_sec": 60},
        headers=headers_b,
    )
    assert resp.status_code == 404
