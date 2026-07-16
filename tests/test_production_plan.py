"""Tests for the ProductionPlan v0 schema module."""
import pytest

from agent_video.production_plan import (
    PLAN_VERSION,
    PlanScene,
    PlanSection,
    PlanValidationError,
    ProductionPlan,
    load_plan,
    write_plan,
)


def _scene(n=1):
    return PlanScene(name=f"scene_{n:02d}", text=f"Narration {n}", asset=f"img_{n}.png")


def _plan(**overrides):
    fields = dict(
        title="Test Episode",
        description="desc",
        tags=["a", "b"],
        sections=[
            PlanSection(id="opening", title="Opening", scenes=[_scene(1), _scene(2)],
                        mood="suspense", intensity=0.4, music_profile="suspense-low"),
            PlanSection(id="collapse", title="Collapse", scenes=[_scene(3)]),
        ],
    )
    fields.update(overrides)
    return ProductionPlan(**fields)


def test_valid_plan_passes_validation():
    _plan().validate()


def test_version_constant_in_dict():
    data = _plan().to_dict()
    assert data["version"] == PLAN_VERSION == "0.1"


def test_to_dict_shape():
    data = _plan().to_dict()
    assert data["episode"] == {"title": "Test Episode", "description": "desc", "tags": ["a", "b"]}
    assert [s["id"] for s in data["sections"]] == ["opening", "collapse"]
    assert data["sections"][0]["mood"] == "suspense"
    assert data["sections"][0]["intensity"] == 0.4
    assert data["sections"][0]["music_profile"] == "suspense-low"
    assert data["sections"][1]["mood"] is None
    assert data["sections"][0]["scenes"][0] == {
        "name": "scene_01", "text": "Narration 1", "asset": "img_1.png"
    }


def test_dict_round_trip():
    plan = _plan()
    assert ProductionPlan.from_dict(plan.to_dict()) == plan


def test_json_file_round_trip(tmp_path):
    plan = _plan()
    path = str(tmp_path / "production_plan.json")
    write_plan(plan, path)
    assert load_plan(path) == plan


def test_flatten_scenes_document_order():
    names = [s.name for s in _plan().flatten_scenes()]
    assert names == ["scene_01", "scene_02", "scene_03"]


def test_no_sections_rejected():
    with pytest.raises(PlanValidationError, match="no sections"):
        _plan(sections=[]).validate()


def test_empty_section_rejected():
    bad = _plan(sections=[PlanSection(id="empty", title="Empty", scenes=[])])
    with pytest.raises(PlanValidationError, match="'empty' has no scenes"):
        bad.validate()


def test_duplicate_section_ids_rejected():
    bad = _plan(sections=[
        PlanSection(id="dup", title="A", scenes=[_scene(1)]),
        PlanSection(id="dup", title="B", scenes=[_scene(2)]),
    ])
    with pytest.raises(PlanValidationError, match="duplicate section id 'dup'"):
        bad.validate()


def test_duplicate_scene_names_rejected_across_sections():
    bad = _plan(sections=[
        PlanSection(id="a", title="A", scenes=[_scene(1)]),
        PlanSection(id="b", title="B", scenes=[_scene(1)]),
    ])
    with pytest.raises(PlanValidationError, match="duplicate scene name 'scene_01'"):
        bad.validate()


@pytest.mark.parametrize("field_name", ["name", "text", "asset"])
def test_blank_scene_field_rejected(field_name):
    scene = _scene(1)
    setattr(scene, field_name, "  ")
    bad = _plan(sections=[PlanSection(id="a", title="A", scenes=[scene])])
    with pytest.raises(PlanValidationError, match=field_name):
        bad.validate()


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_intensity_out_of_range_rejected(value):
    bad = _plan(sections=[
        PlanSection(id="a", title="A", scenes=[_scene(1)], intensity=value),
    ])
    with pytest.raises(PlanValidationError, match="intensity"):
        bad.validate()


def test_from_dict_malformed_raises():
    with pytest.raises(PlanValidationError, match="malformed"):
        ProductionPlan.from_dict({"version": "0.1", "sections": []})


def test_from_dict_validates():
    data = _plan().to_dict()
    data["sections"][0]["scenes"] = []
    with pytest.raises(PlanValidationError, match="has no scenes"):
        ProductionPlan.from_dict(data)
