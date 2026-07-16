"""One whole-episode LLM pass that critiques narration naturalness and genre consistency."""
from __future__ import annotations

from agent_video.production_plan import ProductionPlan
from agent_video.script_quality import QualityFlag, SceneCritique

from .client import AIError, generate_json

LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def _format_narration(plan: ProductionPlan) -> str:
    return "\n\n".join(f"[{scene.name}] {scene.text}" for scene in plan.flatten_scenes())


def _format_hints(flags: list[QualityFlag]) -> str:
    if not flags:
        return "(none)"
    by_scene: dict[str, list[QualityFlag]] = {}
    for flag in flags:
        by_scene.setdefault(flag.scene_name, []).append(flag)
    lines = []
    for scene_name, scene_flags in by_scene.items():
        reasons = "; ".join(f"{f.rule_id} — {f.reason}" for f in scene_flags)
        lines.append(f"{scene_name}: {reasons}")
    return "\n".join(lines)


def critique_script(plan: ProductionPlan, flags: list[QualityFlag], language: str) -> list[SceneCritique]:
    language_name = LANGUAGE_NAMES.get(language, language)
    system = (
        "You are a script editor reviewing narration for a narrated YouTube video, written in "
        f"{language_name}. Read the FULL episode below for tone, genre consistency, and "
        "natural spoken delivery. Flag scenes with real problems: formulaic AI-sounding "
        "prose, abstract commentary that tells the audience how to feel instead of showing an "
        "event, or a scene that breaks the episode's established genre/format. A list of "
        "automated hints is provided below — use them as a starting point, but also flag "
        "scenes the hints missed, and don't flag a hinted scene if it reads fine in context. "
        "Do not flag every scene — most scenes should have no issue at all. "
        'Reply with ONLY JSON: {"critiques": [{"scene_name": str, "issue": str, "reason": str, '
        '"rewrite_suggestion": str, "severity": 1|2|3}]}'
    )
    user = (
        f"Full narration:\n{_format_narration(plan)}\n\n"
        f"Automated hints (scene: matched rule — reason):\n{_format_hints(flags)}"
    )
    result = generate_json(system, user, max_tokens=8192)

    raw_critiques = result.get("critiques")
    if not isinstance(raw_critiques, list):
        raise AIError("Model reply missing 'critiques' list")

    valid_names = {scene.name for scene in plan.flatten_scenes()}

    critiques: list[SceneCritique] = []
    for raw in raw_critiques:
        if not isinstance(raw, dict):
            raise AIError("Critique entry is not an object")
        try:
            scene_name = raw["scene_name"]
            issue = raw["issue"]
            reason = raw["reason"]
            rewrite_suggestion = raw["rewrite_suggestion"]
            severity = raw["severity"]
        except KeyError as exc:
            raise AIError(f"Critique entry missing required field: {exc}") from exc
        if not isinstance(scene_name, str) or not scene_name.strip():
            raise AIError("Critique entry has invalid scene_name")
        if scene_name not in valid_names:
            raise AIError(f"Critique entry references unknown scene_name: {scene_name!r}")
        if not isinstance(issue, str) or not isinstance(reason, str) or not isinstance(rewrite_suggestion, str):
            raise AIError("Critique entry has a non-string text field")
        if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 3:
            raise AIError(f"Critique entry has invalid severity: {severity!r}")
        critiques.append(
            SceneCritique(
                scene_name=scene_name,
                issue=issue,
                reason=reason,
                rewrite_suggestion=rewrite_suggestion,
                severity=severity,
            )
        )
    return critiques
