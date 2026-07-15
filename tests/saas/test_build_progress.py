"""Build observability: job stage/progress updates and latest-job endpoint."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


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


def test_job_has_stage_column(db_session):
    user = User(email="u@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    episode = Episode(user_id=user.id, title="EP")
    db_session.add(episode)
    db_session.commit()
    job = Job(episode_id=episode.id, type="build", stage="tts 3/10")
    db_session.add(job)
    db_session.commit()
    assert db_session.query(Job).one().stage == "tts 3/10"


def test_run_build_updates_stage_and_progress(db_session_factory, tmp_path, monkeypatch):
    db = db_session_factory()
    user = User(email="u@example.com", password_hash="x")
    db.add(user)
    db.commit()
    episode = Episode(user_id=user.id, title="EP")
    episode.scenes.append(Scene(order_index=0, narration_text="one", asset_object_key="a/0.png"))
    episode.scenes.append(Scene(order_index=1, narration_text="two", asset_object_key="a/1.png"))
    db.add(episode)
    db.commit()
    job = Job(episode_id=episode.id, type="build")
    db.add(job)
    db.commit()
    job_id, episode_id = job.id, episode.id
    db.close()

    seen = []

    def fake_download(key, path):
        with open(path, "wb") as f:
            f.write(b"x")

    class FakeTTS:
        def synthesize(self, text, out_path, voice, language, style=0.0):
            with open(out_path, "wb") as f:
                f.write(b"mp3")

    def snapshot(*args, **kwargs):
        check = db_session_factory()
        j = check.query(Job).filter_by(id=job_id).one()
        seen.append((j.stage, j.progress_pct))
        check.close()
        return 1.0

    with patch("saas.tasks.download_to_path", side_effect=fake_download), \
         patch("saas.tasks.get_tts_provider", return_value=FakeTTS()), \
         patch("saas.tasks.get_audio_duration", side_effect=snapshot), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(tmp_path / "out.mp4")) as fake_build, \
         patch("saas.tasks.save_output", return_value="episodes/1/output.mp4"):
        (tmp_path / "out.mp4").write_bytes(b"mp4")
        run_build(job_id, db_session_factory)

    # get_audio_duration runs right after each scene's TTS; the stage
    # committed at that moment must name the tts phase and count scenes.
    assert seen[0][0] == "tts 1/2"
    assert seen[1][0] == "tts 2/2"
    assert seen[1][1] >= seen[0][1]

    final = db_session_factory()
    j = final.query(Job).filter_by(id=job_id).one()
    assert j.status == "done"
    assert j.progress_pct == 100
    final.close()


def test_latest_job_endpoint(client):
    headers = _auth(client)
    ep_id = client.post("/episodes", json={"title": "EP", "scenes": []}, headers=headers).json()["id"]

    assert client.get(f"/episodes/{ep_id}/jobs/latest", headers=headers).status_code == 404

    # Two build jobs — latest must win
    from saas.models import Job as JobModel
    db = app.dependency_overrides[get_db]().__next__()
    db.add(JobModel(episode_id=ep_id, type="build", status="failed", error_message="boom"))
    db.add(JobModel(episode_id=ep_id, type="build", status="running", stage="tts 1/5", progress_pct=10))
    db.commit()

    r = client.get(f"/episodes/{ep_id}/jobs/latest", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    assert body["stage"] == "tts 1/5"


def test_latest_job_is_owner_scoped(client):
    headers_a = _auth(client, "a@example.com")
    headers_b = _auth(client, "b@example.com")
    ep_id = client.post("/episodes", json={"title": "EP", "scenes": []}, headers=headers_a).json()["id"]
    assert client.get(f"/episodes/{ep_id}/jobs/latest", headers=headers_b).status_code == 404
