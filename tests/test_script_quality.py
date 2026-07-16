"""Tests for the deterministic script-quality rule checker."""
from agent_video.production_plan import PlanScene, PlanSection, ProductionPlan
from agent_video.script_quality import QualityFlag, check_plan


def _plan(*scene_texts: str) -> ProductionPlan:
    scenes = [
        PlanScene(name=f"scene_{i:02d}", text=text, asset=f"img_{i}.png")
        for i, text in enumerate(scene_texts, start=1)
    ]
    return ProductionPlan(
        title="T", description="", tags=[],
        sections=[PlanSection(id="main", title="T", scenes=scenes)],
    )


def _rule_ids(flags: list[QualityFlag], scene_name: str) -> set[str]:
    return {f.rule_id for f in flags if f.scene_name == scene_name}


def test_clean_scene_has_no_flags():
    plan = _plan("Long stepped out into the hallway.")
    assert check_plan(plan) == []


def test_cliche_question_no_longer():
    plan = _plan("The question was no longer what is happening.")
    assert "cliche_question_no_longer" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_from_that_moment():
    plan = _plan("From that moment on, everything changed.")
    assert "cliche_from_that_moment" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_little_did():
    plan = _plan("Little did he know what waited behind the door.")
    assert "cliche_little_did" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_whole_new_level():
    plan = _plan("It pushed the panic to a whole new level.")
    assert "cliche_whole_new_level" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_like_never_before():
    plan = _plan("The city was dark like never before.")
    assert "cliche_like_never_before" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_everything_about_to_change():
    plan = _plan("Everything was about to change for good.")
    assert "cliche_everything_about_to_change" in _rule_ids(check_plan(plan), "scene_01")


def test_cliche_officially():
    plan = _plan("Day one of the outbreak officially began for him.")
    assert "cliche_officially" in _rule_ids(check_plan(plan), "scene_01")


def test_structural_not_x_not_y_but_z():
    plan = _plan("Not a storm. Not an earthquake. But something else entirely.")
    assert "structural_not_x_not_y_but_z" in _rule_ids(check_plan(plan), "scene_01")


def test_structural_no_x_no_y():
    plan = _plan("No further details. No explanation. He panicked.")
    assert "structural_no_x_no_y" in _rule_ids(check_plan(plan), "scene_01")


def test_long_sentence():
    long_sentence = " ".join(["word"] * 29) + "."
    plan = _plan(long_sentence)
    assert "long_sentence" in _rule_ids(check_plan(plan), "scene_01")


def test_short_sentence_not_flagged_as_long():
    plan = _plan("He opened the door and stepped inside quietly.")
    assert "long_sentence" not in _rule_ids(check_plan(plan), "scene_01")


def test_rhetorical_ending():
    plan = _plan("How many of them were still, truly, human?")
    assert "rhetorical_ending" in _rule_ids(check_plan(plan), "scene_01")


def test_statement_not_flagged_as_rhetorical():
    plan = _plan("He closed the door behind him.")
    assert "rhetorical_ending" not in _rule_ids(check_plan(plan), "scene_01")


def test_rules_are_case_insensitive():
    plan = _plan("THE QUESTION WAS NO LONGER what is happening.")
    assert "cliche_question_no_longer" in _rule_ids(check_plan(plan), "scene_01")


def test_flag_carries_scene_name_severity_and_matched_text():
    plan = _plan("Little did he know what waited.")
    flags = check_plan(plan)
    flag = next(f for f in flags if f.rule_id == "cliche_little_did")
    assert flag.scene_name == "scene_01"
    assert flag.severity == 3
    assert "little did he know" in flag.matched_text.lower()
    assert flag.reason == "Cliché omniscient foreshadowing"


def test_multiple_flags_on_same_scene():
    plan = _plan("Little did he know the question was no longer simple.")
    ids = _rule_ids(check_plan(plan), "scene_01")
    assert "cliche_little_did" in ids
    assert "cliche_question_no_longer" in ids
