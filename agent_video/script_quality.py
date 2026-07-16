"""Deterministic + LLM-assisted narration quality checks over a ProductionPlan."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .production_plan import ProductionPlan


@dataclass
class QualityFlag:
    scene_name: str
    rule_id: str
    severity: int
    matched_text: str
    reason: str


@dataclass
class Rule:
    id: str
    pattern: re.Pattern
    severity: int
    reason: str


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


RULES: list[Rule] = [
    Rule("cliche_question_no_longer", _rx(r"the question was no longer"), 3,
         "Formulaic dramatic contrast"),
    Rule("cliche_from_that_moment", _rx(r"from that moment (on|forward)"), 2,
         "Generic turning-point narration"),
    Rule("cliche_little_did", _rx(r"little did \w+ know"), 3,
         "Cliché omniscient foreshadowing"),
    Rule("cliche_whole_new_level", _rx(r"(a )?whole new level"), 2,
         "Generic intensifier"),
    Rule("cliche_like_never_before", _rx(r"like (never|nothing) before"), 2,
         "Generic dramatic exaggeration"),
    Rule("cliche_everything_about_to_change", _rx(r"everything (was|is) about to change"), 2,
         "Generic dramatic setup"),
    Rule("cliche_officially", _rx(r"officially (began|started)"), 2,
         "Narrator declares a turning point instead of showing it"),
    Rule("structural_not_x_not_y_but_z",
         _rx(r"not\s+\w[^.]*\.\s*not\s+\w[^.]*\.\s*but\b"), 2,
         "Repeated triplet-contrast sentence structure"),
    Rule("structural_no_x_no_y", _rx(r"\bno\s+[^.!?]+[.!?]\s+no\s+[^.!?]+[.!?]"), 1,
         "Repeated sentence-fragment structure"),
]

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_LONG_SENTENCE_WORD_LIMIT = 28


def _check_long_sentences(scene_name: str, text: str) -> list[QualityFlag]:
    flags = []
    for raw_sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = raw_sentence.strip()
        if not sentence:
            continue
        word_count = len(sentence.split())
        if word_count > _LONG_SENTENCE_WORD_LIMIT:
            flags.append(
                QualityFlag(
                    scene_name=scene_name,
                    rule_id="long_sentence",
                    severity=1,
                    matched_text=sentence,
                    reason="Hard to speak aloud / read as one breath",
                )
            )
    return flags


def _check_rhetorical_ending(scene_name: str, text: str) -> list[QualityFlag]:
    stripped = text.strip()
    if stripped.endswith("?"):
        return [
            QualityFlag(
                scene_name=scene_name,
                rule_id="rhetorical_ending",
                severity=1,
                matched_text=stripped,
                reason="Rhetorical-question ending (fine occasionally, a tell in density)",
            )
        ]
    return []


def check_plan(plan: ProductionPlan) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    for scene in plan.flatten_scenes():
        for rule in RULES:
            match = rule.pattern.search(scene.text)
            if match:
                flags.append(
                    QualityFlag(
                        scene_name=scene.name,
                        rule_id=rule.id,
                        severity=rule.severity,
                        matched_text=match.group(0),
                        reason=rule.reason,
                    )
                )
        flags.extend(_check_long_sentences(scene.name, scene.text))
        flags.extend(_check_rhetorical_ending(scene.name, scene.text))
    return flags
