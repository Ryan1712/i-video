import pytest
from sqlalchemy.exc import IntegrityError

from saas.models import Episode, Job, Scene, User, YouTubeConnection


def test_create_user(db_session):
    user = User(email="a@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()

    fetched = db_session.query(User).filter_by(email="a@example.com").one()
    assert fetched.role == "user"
    assert fetched.created_at is not None


def test_episode_with_scenes_relationship(db_session):
    user = User(email="b@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(
        user_id=user.id,
        title="What If The Moon Disappeared",
        description="desc",
        tags="whatif,space",
        status="draft",
    )
    episode.scenes.append(Scene(order_index=0, narration_text="Scene one text"))
    episode.scenes.append(Scene(order_index=1, narration_text="Scene two text"))
    db_session.add(episode)
    db_session.commit()

    fetched = db_session.query(Episode).filter_by(title="What If The Moon Disappeared").one()
    assert fetched.status == "draft"
    assert fetched.output_object_key is None
    assert len(fetched.scenes) == 2
    assert fetched.scenes[0].narration_text == "Scene one text"
    assert fetched.scenes[0].asset_object_key is None
    assert fetched.youtube_video_id is None


def test_job_defaults(db_session):
    user = User(email="c@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()
    episode = Episode(user_id=user.id, title="T", description="", tags="", status="draft")
    db_session.add(episode)
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()

    fetched = db_session.query(Job).filter_by(episode_id=episode.id).one()
    assert fetched.progress_pct == 0
    assert fetched.error_message is None


def test_youtube_connection_model(db_session):
    user = User(email="yt@example.com", password_hash="hashed", role="user")
    db_session.add(user)
    db_session.commit()

    conn = YouTubeConnection(
        user_id=user.id,
        channel_id="UC_test_channel",
        channel_title="Test Channel",
        encrypted_refresh_token="enc_token_abc",
    )
    db_session.add(conn)
    db_session.commit()

    fetched = db_session.query(YouTubeConnection).filter_by(user_id=user.id).one()
    assert fetched.channel_id == "UC_test_channel"
    assert fetched.channel_title == "Test Channel"
    assert fetched.encrypted_refresh_token == "enc_token_abc"
    assert fetched.created_at is not None

    # UNIQUE constraint on user_id — second connection for same user must fail
    dup = YouTubeConnection(
        user_id=user.id,
        channel_id="UC_other",
        channel_title="Other",
        encrypted_refresh_token="enc_token_xyz",
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        db_session.commit()
