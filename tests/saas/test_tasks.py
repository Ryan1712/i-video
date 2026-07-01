# tests/saas/test_tasks.py
from unittest.mock import patch

from moto import mock_aws

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def _make_episode_with_one_scene(db_session, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="e@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Test Episode", description="", tags="", status="ready")
    scene = Scene(order_index=0, narration_text="Hello world", asset_object_key=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    key = f"episodes/{episode.id}/scenes/{scene.id}.png"
    upload_bytes(key, b"fake-png-bytes")
    scene.asset_object_key = key
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    return episode.id, job.id


@mock_aws
def test_run_build_succeeds_and_updates_episode_and_job(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, monkeypatch)

    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")

    with patch("saas.tasks.synthesize_scene") as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip") as clip_mock, \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)) as build_ep_mock:
        run_build(job_id, db_session_factory)

    assert synth_mock.called
    assert clip_mock.called
    assert build_ep_mock.called

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "done"
    assert job.progress_pct == 100
    assert episode.status == "built"
    assert episode.output_object_key == f"episodes/{episode_id}/output.mp4"

    from saas.object_storage import get_s3_client

    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=episode.output_object_key)["Body"].read()
    assert body == b"fake-mp4-bytes"
    fresh.close()


@mock_aws
def test_run_build_marks_job_failed_on_exception(db_session, db_session_factory, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, monkeypatch)

    with patch("saas.tasks.synthesize_scene", side_effect=RuntimeError("ElevenLabs exploded")):
        run_build(job_id, db_session_factory)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "failed"
    assert "ElevenLabs exploded" in job.error_message
    assert episode.status == "draft"
    fresh.close()
