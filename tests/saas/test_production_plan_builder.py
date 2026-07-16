"""Tests for building a ProductionPlan from an existing DB episode (no render needed)."""
from saas.models import Episode, Scene, User
from saas.production_plan_builder import build_plan_from_db_episode


def test_build_plan_from_db_episode(db_session):
    user = User(email="plan-builder@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(
        user_id=user.id, title="Plan Builder Test", description="d", tags="a, b", status="ready"
    )
    episode.scenes.append(
        Scene(order_index=0, narration_text="Hello world", asset_object_key="episodes/1/scenes/1.png")
    )
    episode.scenes.append(
        Scene(order_index=1, narration_text="Second line", asset_object_key="episodes/1/scenes/2.png")
    )
    db_session.add(episode)
    db_session.commit()

    plan = build_plan_from_db_episode(episode)
    plan.validate()

    assert plan.title == "Plan Builder Test"
    assert plan.description == "d"
    assert plan.tags == ["a", "b"]
    assert [s.id for s in plan.sections] == ["main"]
    assert plan.sections[0].title == "Plan Builder Test"
    scenes = plan.flatten_scenes()
    assert [s.name for s in scenes] == ["scene_00", "scene_01"]
    assert [s.text for s in scenes] == ["Hello world", "Second line"]
    assert [s.asset for s in scenes] == ["episodes/1/scenes/1.png", "episodes/1/scenes/2.png"]


def test_build_plan_from_db_episode_no_tags(db_session):
    user = User(email="plan-builder2@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="No Tags", description="", tags="", status="ready")
    episode.scenes.append(
        Scene(order_index=0, narration_text="Only line", asset_object_key="k.png")
    )
    db_session.add(episode)
    db_session.commit()

    plan = build_plan_from_db_episode(episode)
    assert plan.tags == []
