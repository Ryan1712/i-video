from saas.models import Episode, Series, SeriesAsset, User


def _make_user(db_session, email="owner@example.com"):
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def test_episode_has_script_fields(db_session):
    user = _make_user(db_session)
    episode = Episode(
        user_id=user.id,
        title="EP1",
        brief="Zombie outbreak starts in a small town",
        script="Full narration text...",
        target_duration_sec=480,
    )
    db_session.add(episode)
    db_session.commit()

    loaded = db_session.query(Episode).one()
    assert loaded.brief.startswith("Zombie")
    assert loaded.script == "Full narration text..."
    assert loaded.target_duration_sec == 480


def test_episode_script_fields_default_empty(db_session):
    user = _make_user(db_session)
    db_session.add(Episode(user_id=user.id, title="EP1"))
    db_session.commit()
    loaded = db_session.query(Episode).one()
    assert loaded.brief == ""
    assert loaded.script == ""
    assert loaded.target_duration_sec is None


def test_series_asset_source_defaults_to_uploaded(db_session):
    user = _make_user(db_session)
    series = Series(user_id=user.id, name="S1")
    series.assets.append(SeriesAsset(kind="character", name="hero"))
    db_session.add(series)
    db_session.commit()
    assert db_session.query(SeriesAsset).one().source == "uploaded"
