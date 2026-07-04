from saas.models import Episode, Scene, Series, SeriesAsset, User


def _make_user(db_session, email="owner@example.com"):
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def test_series_with_assets_roundtrip(db_session):
    user = _make_user(db_session)
    series = Series(
        user_id=user.id,
        name="What if zombies",
        description="10-episode zombie apocalypse series",
        style={"voice_id": "abc", "caption_style": "bold"},
    )
    series.assets.append(
        SeriesAsset(kind="character", name="main_character",
                    description="Stick figure man, torn jacket", object_key="series/1/assets/1.png")
    )
    db_session.add(series)
    db_session.commit()

    loaded = db_session.query(Series).one()
    assert loaded.style["voice_id"] == "abc"
    assert loaded.assets[0].kind == "character"
    assert loaded.assets[0].series_id == loaded.id


def test_episode_links_to_series_and_scene_has_asset_brief(db_session):
    user = _make_user(db_session)
    series = Series(user_id=user.id, name="S1")
    db_session.add(series)
    db_session.commit()

    episode = Episode(user_id=user.id, title="EP1", series_id=series.id)
    episode.scenes.append(
        Scene(order_index=0, narration_text="intro", asset_brief="Bedroom at dawn, stick figure waking up")
    )
    db_session.add(episode)
    db_session.commit()

    loaded = db_session.query(Episode).one()
    assert loaded.series_id == series.id
    assert loaded.scenes[0].asset_brief.startswith("Bedroom")


def test_episode_series_id_is_optional(db_session):
    user = _make_user(db_session)
    episode = Episode(user_id=user.id, title="standalone")
    db_session.add(episode)
    db_session.commit()
    assert db_session.query(Episode).one().series_id is None
