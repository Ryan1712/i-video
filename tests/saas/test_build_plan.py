"""SaaS build task persists a ProductionPlan artifact to object storage."""
import json
from unittest.mock import patch

from moto import mock_aws

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def _fake_synth(text, out_path, api_key, voice_id, style=0.0):
    with open(out_path, "wb") as f:
        f.write(b"audio:" + text.encode("utf-8"))


def _make_episode(db_session, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="plan@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Plan Test", description="d", tags="a,b", status="ready")
    for index, narration in enumerate(["Hello world", "Second line"]):
        episode.scenes.append(
            Scene(order_index=index, narration_text=narration, asset_object_key=None)
        )
    db_session.add(episode)
    db_session.commit()

    for scene in episode.scenes:
        key = f"episodes/{episode.id}/scenes/{scene.id}.png"
        upload_bytes(key, b"fake-png-bytes")
        scene.asset_object_key = key
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()
    return episode, job.id


def _run(job_id, db_session_factory, tmp_path):
    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")
    with patch("saas.tts_providers.synthesize_scene", side_effect=_fake_synth), \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)):
        run_build(job_id, db_session_factory)


@mock_aws
def test_build_uploads_production_plan(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, job_id = _make_episode(db_session, monkeypatch)

    _run(job_id, db_session_factory, tmp_path)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    assert job.status == "done"
    fresh.close()

    from saas.object_storage import get_s3_client

    body = get_s3_client().get_object(
        Bucket="whatif-test-bucket", Key=f"episodes/{episode.id}/production_plan.json"
    )["Body"].read()
    data = json.loads(body)
    assert data["version"] == "0.1"
    assert data["episode"]["title"] == "Plan Test"
    assert data["episode"]["tags"] == ["a", "b"]
    assert len(data["sections"]) == 1
    section = data["sections"][0]
    assert section["id"] == "main"
    assert [s["name"] for s in section["scenes"]] == ["scene_00", "scene_01"]
    assert [s["text"] for s in section["scenes"]] == ["Hello world", "Second line"]
    assert all(s["asset"].startswith(f"episodes/{episode.id}/scenes/") for s in section["scenes"])


@mock_aws
def test_plan_upload_failure_does_not_fail_build(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, job_id = _make_episode(db_session, monkeypatch)

    with patch("saas.tasks.upload_bytes", side_effect=RuntimeError("s3 down")):
        _run(job_id, db_session_factory, tmp_path)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode_row = fresh.query(Episode).filter_by(id=episode.id).one()
    assert job.status == "done"
    assert episode_row.status == "built"
    fresh.close()
