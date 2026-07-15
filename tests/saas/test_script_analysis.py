import pytest
from fastapi.testclient import TestClient

import saas.ai.script_analysis as sa
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


CATALOG = [
    {"id": 7, "kind": "character", "name": "hero", "description": "stick figure man"},
]


def test_analyze_script_passes_catalog_and_normalizes(monkeypatch):
    captured = {}

    def fake_generate_json(system, user_message, max_tokens=8192):
        captured["system"] = system
        return {
            "scenes": [
                {"narration_text": "Scene one.", "asset_id": 7, "asset_brief": None},
                {"narration_text": "Scene two.", "asset_id": 999, "asset_brief": None},
                {"narration_text": "Scene three.", "asset_id": None,
                 "asset_brief": "Ruined city street at dawn"},
            ]
        }

    monkeypatch.setattr(sa, "generate_json", fake_generate_json)
    scenes = sa.analyze_script("script text", "en", CATALOG)

    assert scenes[0] == {"narration_text": "Scene one.", "asset_id": 7, "asset_brief": None}
    # Unknown asset id 999 → treated as missing, with a non-empty brief.
    assert scenes[1]["asset_id"] is None
    assert scenes[1]["asset_brief"]
    assert scenes[2]["asset_brief"] == "Ruined city street at dawn"
    assert "hero" in captured["system"]


def test_analyze_script_rejects_empty_scenes(monkeypatch):
    monkeypatch.setattr(sa, "generate_json", lambda *a, **k: {"scenes": []})
    with pytest.raises(AIError):
        sa.analyze_script("s", "en", [])


def test_analyze_script_rejects_non_object_scene_entry(monkeypatch):
    monkeypatch.setattr(sa, "generate_json", lambda *a, **k: {"scenes": ["just a string"]})
    with pytest.raises(AIError):
        sa.analyze_script("s", "en", [])


def _episode_with_series(client, headers):
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    ep_id = client.post(
        "/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers
    ).json()["id"]
    return sid, ep_id


def test_endpoint_replaces_scenes_and_copies_matched_object_key(client, monkeypatch):
    headers = _auth(client)
    sid, ep_id = _episode_with_series(client, headers)

    # Insert a series asset with a known object_key directly through the DB layer
    # used by the app: upload route needs S3, so patch storage instead.
    monkeypatch.setattr(
        "saas.routers.series.save_series_asset", lambda *a, **k: "series/1/assets/1.png"
    )
    asset = client.post(
        f"/series/{sid}/assets",
        files={"file": ("hero.png", b"png-bytes", "image/png")},
        data={"kind": "location", "name": "hero", "description": "stick figure"},
        headers=headers,
    ).json()

    def fake_analyze(script, language, asset_catalog):
        assert asset_catalog[0]["name"] == "hero"
        return [
            {"narration_text": "One.", "asset_id": asset["id"], "asset_brief": None},
            {"narration_text": "Two.", "asset_id": None, "asset_brief": "A dark forest"},
        ]

    monkeypatch.setattr(episodes_router, "analyze_script", fake_analyze)

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "full script"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["script"] == "full script"
    assert len(body["scenes"]) == 2
    assert body["scenes"][0]["asset_object_key"] == "series/1/assets/1.png"
    assert body["scenes"][1]["asset_object_key"] is None
    assert body["scenes"][1]["asset_brief"] == "A dark forest"


def test_endpoint_only_sends_location_and_generated_assets_to_ai(client, monkeypatch):
    headers = _auth(client)
    sid = client.post("/series", json={"name": "S"}, headers=headers).json()["id"]
    ep_id = client.post(
        "/episodes", json={"title": "EP1", "series_id": sid, "scenes": []}, headers=headers
    ).json()["id"]

    monkeypatch.setattr(
        "saas.routers.series.save_series_asset", lambda *a, **k: "series/1/assets/1.png"
    )

    def _upload(kind, name):
        return client.post(
            f"/series/{sid}/assets",
            files={"file": ("a.png", b"png-bytes", "image/png")},
            data={"kind": kind, "name": name, "description": name},
            headers=headers,
        ).json()

    location_asset = _upload("location", "bedroom")
    character_asset = _upload("character", "hero")
    object_asset = _upload("object", "flashlight")

    captured = {}

    def fake_analyze(script, language, asset_catalog):
        captured["catalog"] = asset_catalog
        return [{"narration_text": "One.", "asset_id": None, "asset_brief": "A scene"}]

    monkeypatch.setattr(episodes_router, "analyze_script", fake_analyze)

    client.post(f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers)

    sent_ids = {a["id"] for a in captured["catalog"]}
    assert location_asset["id"] in sent_ids
    assert character_asset["id"] not in sent_ids
    assert object_asset["id"] not in sent_ids


def test_endpoint_conflicts_when_not_draft(client, monkeypatch):
    headers = _auth(client)
    _, ep_id = _episode_with_series(client, headers)
    # Force status past draft via the analyze path being blocked: mark built through DB.
    from saas.models import Episode
    db = client.app.dependency_overrides[get_db]().__next__()
    db.query(Episode).filter_by(id=ep_id).update({"status": "built"})
    db.commit()

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ERR_EPISODE_NOT_DRAFT"


def test_endpoint_maps_aierror_to_502(client, monkeypatch):
    def boom(script, language, asset_catalog):
        raise AIError("x")

    monkeypatch.setattr(episodes_router, "analyze_script", boom)
    headers = _auth(client)
    _, ep_id = _episode_with_series(client, headers)

    resp = client.post(
        f"/episodes/{ep_id}/analyze-script", json={"script": "s"}, headers=headers
    )
    assert resp.status_code == 502
    assert resp.json()["detail"] == "ERR_SCRIPT_ANALYSIS_FAILED"
