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
class SceneCritique:
    scene_name: str
    issue: str
    reason: str
    rewrite_suggestion: str
    severity: int


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


_INTENSIFIER_WORDS = [
    "panic", "chaos", "suddenly", "completely", "nightmare",
    "terrifying", "desperate", "truly",
]


def _check_repeated_intensifiers(plan: ProductionPlan) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    seen_words: set[str] = set()
    for scene in plan.flatten_scenes():
        for word in _INTENSIFIER_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", scene.text, re.IGNORECASE):
                if word in seen_words:
                    flags.append(
                        QualityFlag(
                            scene_name=scene.name,
                            rule_id="repeated_intensifier",
                            severity=1,
                            matched_text=word,
                            reason=(
                                "Same intensifier reused across the episode instead of "
                                "varying description"
                            ),
                        )
                    )
                seen_words.add(word)
    return flags


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
    flags.extend(_check_repeated_intensifiers(plan))
    return flags


def render_quality_report(
    plan: ProductionPlan, flags: list[QualityFlag], critiques: list[SceneCritique]
) -> str:
    flags_by_scene: dict[str, list[QualityFlag]] = {}
    for flag in flags:
        flags_by_scene.setdefault(flag.scene_name, []).append(flag)
    critiques_by_scene: dict[str, list[SceneCritique]] = {}
    for critique in critiques:
        critiques_by_scene.setdefault(critique.scene_name, []).append(critique)

    all_scenes = plan.flatten_scenes()
    flagged_names = set(flags_by_scene) | set(critiques_by_scene)
    lines = [
        f"# Script Quality Report — {plan.title}",
        "",
        f"Tổng số scene: {len(all_scenes)}",
        f"Scene bị gắn cờ: {len(flagged_names)}",
        "",
    ]
    for scene in all_scenes:
        scene_flags = flags_by_scene.get(scene.name, [])
        scene_critiques = critiques_by_scene.get(scene.name, [])
        if not scene_flags and not scene_critiques:
            continue
        lines.append(f"## {scene.name}")
        lines.append("")
        lines.append(f"Narration: {scene.text}")
        lines.append("")
        for flag in scene_flags:
            lines.append(
                f"- Rule `{flag.rule_id}` (mức {flag.severity}): {flag.reason} "
                f"— khớp: \"{flag.matched_text}\""
            )
        for critique in scene_critiques:
            lines.append(f"- **Issue** (mức {critique.severity}): {critique.issue}")
            lines.append(f"  - Lý do: {critique.reason}")
            lines.append(f"  - Gợi ý viết lại: {critique.rewrite_suggestion}")
            lines.append("  - [ ] Áp dụng gợi ý trên")
        lines.append("")
    return "\n".join(lines)
