from saas.models import Episode, Job, Scene, User


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
