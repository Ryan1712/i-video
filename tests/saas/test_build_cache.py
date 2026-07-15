"""Integration: SaaS build task reuses cached TTS audio across builds."""
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


def _make_episode(db_session, monkeypatch, narrations=("Hello world",)):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="cache@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Cache Test", description="", tags="", status="ready")
    scenes = [
        Scene(order_index=i, narration_text=text, asset_object_key=None)
        for i, text in enumerate(narrations)
    ]
    for scene in scenes:
        episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    for scene in scenes:
        key = f"episodes/{episode.id}/scenes/{scene.id}.png"
        upload_bytes(key, b"fake-png-bytes")
        scene.asset_object_key = key
    db_session.commit()
    return episode, scenes


def _new_build_job(db_session, episode_id):
    job = Job(episode_id=episode_id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()
    return job.id


def _run(job_id, db_session_factory, tmp_path):
    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")
    with patch("saas.tts_providers.synthesize_scene", side_effect=_fake_synth) as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)):
        run_build(job_id, db_session_factory)
    return synth_mock


@mock_aws
def test_second_build_makes_zero_tts_calls(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, _ = _make_episode(db_session, monkeypatch)

    synth1 = _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path)
    assert synth1.call_count == 1

    # reset episode so it can build again
    episode.status = "ready"
    db_session.commit()

    synth2 = _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path)
    assert synth2.call_count == 0

    fresh = db_session_factory()
    assert fresh.query(Job).filter_by(episode_id=episode.id).order_by(Job.id.desc()).first().status == "done"
    fresh.close()


@mock_aws
def test_changed_narration_synthesizes_only_changed_scene(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, scenes = _make_episode(db_session, monkeypatch, narrations=("Hello world", "Second scene line"))

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 2

    scenes[0].narration_text = "Hello again"
    episode.status = "ready"
    db_session.commit()

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1


@mock_aws
def test_tts_cache_off_disables_cache(db_session, db_session_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_CACHE", "off")
    episode, _ = _make_episode(db_session, monkeypatch)

    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1
    episode.status = "ready"
    db_session.commit()
    assert _run(_new_build_job(db_session, episode.id), db_session_factory, tmp_path).call_count == 1
