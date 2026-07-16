"""Tests for the whole-episode LLM naturalness critic."""
from unittest.mock import patch

import pytest

from agent_video.production_plan import PlanScene, PlanSection, ProductionPlan
from agent_video.script_quality import QualityFlag, SceneCritique
from saas.ai.client import AIError
from saas.ai.script_quality_critic import critique_script


def _plan():
    scenes = [
        PlanScene(name="scene_01", text="Long got ready for work.", asset="a.png"),
        PlanScene(name="scene_02", text="The question was no longer simple.", asset="b.png"),
    ]
    return ProductionPlan(title="EP", description="", tags=[], sections=[PlanSection(id="main", title="EP", scenes=scenes)])


def _flags():
    return [
        QualityFlag(
            scene_name="scene_02", rule_id="cliche_question_no_longer", severity=3,
            matched_text="The question was no longer", reason="Formulaic dramatic contrast",
        )
    ]


def test_critique_script_sends_full_narration_and_hints():
    with patch("saas.ai.script_quality_critic.generate_json", return_value={"critiques": []}) as mock:
        critique_script(_plan(), _flags(), language="en")

    system, user = mock.call_args[0][0], mock.call_args[0][1]
    assert "Long got ready for work." in user
    assert "The question was no longer simple." in user
    assert "scene_01" in user and "scene_02" in user
    assert "cliche_question_no_longer" in user
    assert "English" in system


def test_critique_script_parses_valid_response():
    response = {
        "critiques": [
            {
                "scene_name": "scene_02",
                "issue": "Formulaic contrast",
                "reason": "Overused turning-point phrase",
                "rewrite_suggestion": "Everything had changed since the alert.",
                "severity": 3,
            }
        ]
    }
    with patch("saas.ai.script_quality_critic.generate_json", return_value=response):
        result = critique_script(_plan(), _flags(), language="en")

    assert result == [
        SceneCritique(
            scene_name="scene_02",
            issue="Formulaic contrast",
            reason="Overused turning-point phrase",
            rewrite_suggestion="Everything had changed since the alert.",
            severity=3,
        )
    ]


def test_critique_script_empty_critiques_list_is_valid():
    with patch("saas.ai.script_quality_critic.generate_json", return_value={"critiques": []}):
        assert critique_script(_plan(), _flags(), language="en") == []


def test_critique_script_missing_critiques_key_raises():
    with patch("saas.ai.script_quality_critic.generate_json", return_value={}):
        with pytest.raises(AIError, match="critiques"):
            critique_script(_plan(), _flags(), language="en")


def test_critique_script_missing_required_field_raises():
    response = {"critiques": [{"scene_name": "scene_02", "issue": "x"}]}
    with patch("saas.ai.script_quality_critic.generate_json", return_value=response):
        with pytest.raises(AIError):
            critique_script(_plan(), _flags(), language="en")


def test_critique_script_wrong_severity_type_raises():
    response = {
        "critiques": [
            {
                "scene_name": "scene_02", "issue": "x", "reason": "y",
                "rewrite_suggestion": "z", "severity": "high",
            }
        ]
    }
    with patch("saas.ai.script_quality_critic.generate_json", return_value=response):
        with pytest.raises(AIError):
            critique_script(_plan(), _flags(), language="en")


def test_critique_script_bool_severity_raises():
    response = {
        "critiques": [
            {
                "scene_name": "scene_02", "issue": "x", "reason": "y",
                "rewrite_suggestion": "z", "severity": True,
            }
        ]
    }
    with patch("saas.ai.script_quality_critic.generate_json", return_value=response):
        with pytest.raises(AIError):
            critique_script(_plan(), _flags(), language="en")


def test_critique_script_unknown_scene_name_raises():
    response = {
        "critiques": [
            {
                "scene_name": "scene_99", "issue": "x", "reason": "y",
                "rewrite_suggestion": "z", "severity": 1,
            }
        ]
    }
    with patch("saas.ai.script_quality_critic.generate_json", return_value=response):
        with pytest.raises(AIError, match="scene_99"):
            critique_script(_plan(), _flags(), language="en")
