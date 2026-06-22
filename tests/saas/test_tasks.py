import os
from unittest.mock import MagicMock, patch

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _make_episode_with_one_scene(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("EPISODES_DIR", str(tmp_path / "episodes"))

    user = User(email="e@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Test Episode", description="", tags="", status="ready")
    scene = Scene(order_index=0, narration_text="Hello world", asset_path=None)
    episode.scenes.append(scene)
    db_session.add(episode)
    db_session.commit()

    asset_dir = tmp_path / "uploads" / "episodes" / str(episode.id) / "scenes"
    asset_dir.mkdir(parents=True)
    (asset_dir / f"{scene.id}.png").write_bytes(b"fake-png-bytes")
    scene.asset_path = os.path.join("episodes", str(episode.id), "scenes", f"{scene.id}.png")
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    return episode.id, job.id


def test_run_build_succeeds_and_updates_episode_and_job(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, tmp_path, monkeypatch)

    with patch("saas.tasks.synthesize_scene") as synth_mock, \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip") as clip_mock, \
         patch("saas.tasks.build_episode", return_value="/fake/output/episode.mp4") as build_ep_mock:
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
    assert episode.output_path is not None
    fresh.close()


def test_run_build_marks_job_failed_on_exception(db_session, db_session_factory, tmp_path, monkeypatch):
    episode_id, job_id = _make_episode_with_one_scene(db_session, tmp_path, monkeypatch)

    with patch("saas.tasks.synthesize_scene", side_effect=RuntimeError("ElevenLabs exploded")):
        run_build(job_id, db_session_factory)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode = fresh.query(Episode).filter_by(id=episode_id).one()
    assert job.status == "failed"
    assert "ElevenLabs exploded" in job.error_message
    assert episode.status == "ready"
    fresh.close()
