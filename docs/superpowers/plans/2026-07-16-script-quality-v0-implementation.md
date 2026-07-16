# Script Quality v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI tool that reads an existing SaaS episode's narration, flags formulaic/AI-tell prose with deterministic rules, sends the whole episode through one LLM critique pass, and writes a human-readable markdown report — with zero write access to the script or plan.

**Architecture:** `agent_video/script_quality.py` (engine, pure Python: rule dataclasses, `check_plan`, `render_quality_report`) has no AI or DB dependency, mirroring how `production_plan.py` stays provider-agnostic. `saas/production_plan_builder.py` extracts the plan-construction logic already inline in `saas/tasks.py::run_build` into a reusable, TTS/render-free function. `saas/ai/script_quality_critic.py` wraps one `generate_json` call, following the exact validation pattern already used in `saas/ai/script_analysis.py`. `scripts/check_script_quality.py` wires the four pieces together as a one-off CLI tool.

**Tech Stack:** Python 3.12, dataclasses, `re`, pytest, `unittest.mock` for the critic tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-script-quality-v0-design.md`

## Global Constraints

- Run tests from repo root `d:\Video\agent_video` with `python -m pytest tests/ -q`. Suite currently passes with 311 tests — all must still pass.
- The tool never writes to `production_plan.json`, the DB, or `script.md` — report-only.
- `saas/tasks.py::run_build` behavior must be provably unchanged by the extraction (existing `tests/saas/test_build_plan.py` and `tests/saas/test_tasks.py` pass unmodified).
- All rule regexes are case-insensitive.
- All commits on branch `script-quality-v0`, end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Rule-based checker (`agent_video/script_quality.py`, part 1)

**Files:**
- Create: `agent_video/script_quality.py`
- Test: `tests/test_script_quality.py`

**Interfaces:**
- Consumes: `ProductionPlan`, `PlanSection`, `PlanScene` from `agent_video.production_plan`.
- Produces (later tasks import all of these from `agent_video.script_quality`):
  - `@dataclass QualityFlag(scene_name: str, rule_id: str, severity: int, matched_text: str, reason: str)`
  - `@dataclass Rule(id: str, pattern: re.Pattern, severity: int, reason: str)`
  - `RULES: list[Rule]` (the 11 per-scene regex rules from the spec table, excluding `repeated_intensifier`)
  - `check_plan(plan: ProductionPlan) -> list[QualityFlag]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_script_quality.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_script_quality.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_video.script_quality'`

- [ ] **Step 3: Write the implementation**

Create `agent_video/script_quality.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_script_quality.py -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add agent_video/script_quality.py tests/test_script_quality.py
git commit -m "feat: add deterministic script-quality rule checker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Plan-wide repeated-intensifier rule + report rendering

**Files:**
- Modify: `agent_video/script_quality.py`
- Test: `tests/test_script_quality.py` (append)

**Interfaces:**
- Consumes: `QualityFlag`, `check_plan` from Task 1.
- Produces: `check_plan` now also applies the plan-wide rule;
  `@dataclass SceneCritique(scene_name: str, issue: str, reason: str, rewrite_suggestion: str, severity: int)`;
  `render_quality_report(plan: ProductionPlan, flags: list[QualityFlag], critiques: list[SceneCritique]) -> str`.
  Later tasks import `SceneCritique` and `render_quality_report` from `agent_video.script_quality`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_script_quality.py`:

```python
from agent_video.script_quality import SceneCritique, render_quality_report

INTENSIFIER_WORDS = [
    "panic", "chaos", "suddenly", "completely", "nightmare", "terrifying", "desperate", "truly",
]


def test_repeated_intensifier_flags_from_second_occurrence():
    plan = _plan(
        "The panic was rising in the street.",
        "Nothing about this felt normal.",
        "Another wave of panic swept through the crowd.",
    )
    flags = check_plan(plan)
    assert "repeated_intensifier" not in _rule_ids(flags, "scene_01")
    assert "repeated_intensifier" in _rule_ids(flags, "scene_03")


def test_repeated_intensifier_distinct_words_do_not_cross_flag():
    plan = _plan("There was chaos everywhere.", "He felt truly alone.")
    flags = check_plan(plan)
    assert _rule_ids(flags, "scene_01") == set()
    assert _rule_ids(flags, "scene_02") == set()


def test_repeated_intensifier_word_boundary_no_false_positive():
    # "panicked" contains "panic" as a substring, but \b must prevent a false match —
    # otherwise two uses of "panicked" would wrongly trigger repetition on the standalone word.
    plan = _plan("He panicked and ran down the hall.", "He panicked again near the door.")
    flags = check_plan(plan)
    assert _rule_ids(flags, "scene_01") == set()
    assert _rule_ids(flags, "scene_02") == set()


def test_render_report_omits_clean_scenes():
    plan = _plan("He walked to the store.", "Little did he know what waited.")
    flags = check_plan(plan)
    report = render_quality_report(plan, flags, critiques=[])
    assert "scene_01" not in report
    assert "scene_02" in report


def test_render_report_includes_summary_counts():
    plan = _plan("He walked to the store.", "Little did he know what waited.")
    flags = check_plan(plan)
    report = render_quality_report(plan, flags, critiques=[])
    assert "Tổng số scene: 2" in report
    assert "Scene bị gắn cờ: 1" in report


def test_render_report_includes_rule_flag_details():
    plan = _plan("Little did he know what waited.")
    flags = check_plan(plan)
    report = render_quality_report(plan, flags, critiques=[])
    assert "cliche_little_did" in report
    assert "Cliché omniscient foreshadowing" in report
    assert "Little did he know" in report


def test_render_report_includes_critique_details():
    plan = _plan("He walked to the store.")
    critique = SceneCritique(
        scene_name="scene_01",
        issue="Flat delivery",
        reason="No sensory detail",
        rewrite_suggestion="He walked to the store, boots crunching over broken glass.",
        severity=2,
    )
    report = render_quality_report(plan, flags=[], critiques=[critique])
    assert "scene_01" in report
    assert "Flat delivery" in report
    assert "No sensory detail" in report
    assert "boots crunching over broken glass" in report
    assert "Áp dụng gợi ý" in report


def test_render_report_scene_with_only_critique_not_omitted():
    plan = _plan("He walked to the store.", "She waited by the door.")
    critique = SceneCritique(
        scene_name="scene_02", issue="x", reason="y", rewrite_suggestion="z", severity=1,
    )
    report = render_quality_report(plan, flags=[], critiques=[critique])
    assert "scene_01" not in report
    assert "scene_02" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_script_quality.py -q`
Expected: FAIL — `ImportError: cannot import name 'SceneCritique'`; repeated-intensifier tests fail (rule not yet applied).

- [ ] **Step 3: Write the implementation**

Add to `agent_video/script_quality.py` (add `from dataclasses import dataclass` already present; no new imports needed beyond what Task 1 added):

```python
@dataclass
class SceneCritique:
    scene_name: str
    issue: str
    reason: str
    rewrite_suggestion: str
    severity: int


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
```

Change `check_plan`'s final line from `return flags` to:

```python
    flags.extend(_check_repeated_intensifiers(plan))
    return flags
```

Append the report renderer:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_script_quality.py -q`
Expected: 25 passed

- [ ] **Step 5: Commit**

```bash
git add agent_video/script_quality.py tests/test_script_quality.py
git commit -m "feat: add repeated-intensifier rule and quality report renderer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `saas/production_plan_builder.py` — extract plan construction from `run_build`

**Files:**
- Create: `saas/production_plan_builder.py`
- Modify: `saas/tasks.py` (`run_build`)
- Test: `tests/saas/test_production_plan_builder.py`

**Interfaces:**
- Consumes: `PlanScene`, `PlanSection`, `ProductionPlan` from `agent_video.production_plan`; `Episode` from `saas.models`.
- Produces: `build_plan_from_db_episode(episode: Episode) -> ProductionPlan`. Task 5's CLI script imports this directly.

- [ ] **Step 1: Write the failing test**

Create `tests/saas/test_production_plan_builder.py`:

```python
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
```

(This test uses the `db_session` fixture already defined in `tests/saas/conftest.py` — the same fixture used by `tests/saas/test_tasks.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/saas/test_production_plan_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saas.production_plan_builder'`

- [ ] **Step 3: Write the implementation**

Create `saas/production_plan_builder.py`:

```python
"""Build a ProductionPlan from an existing DB-backed episode — no TTS or render needed."""
from __future__ import annotations

from agent_video.production_plan import PlanScene, PlanSection, ProductionPlan

from .models import Episode


def build_plan_from_db_episode(episode: Episode) -> ProductionPlan:
    plan_scenes = [
        PlanScene(
            name=f"scene_{scene.order_index:02d}",
            text=scene.narration_text,
            asset=scene.asset_object_key,
        )
        for scene in episode.scenes
    ]
    return ProductionPlan(
        title=episode.title,
        description=episode.description,
        tags=[t.strip() for t in episode.tags.split(",") if t.strip()],
        sections=[PlanSection(id="main", title=episode.title, scenes=plan_scenes)],
    )
```

- [ ] **Step 4: Run the new test**

Run: `python -m pytest tests/saas/test_production_plan_builder.py -q`
Expected: 2 passed

- [ ] **Step 5: Refactor `run_build` to call the new helper**

In `saas/tasks.py`, the current code (lines 17, 54-78) is:

```python
from agent_video.production_plan import PlanScene, PlanSection, ProductionPlan
```

and, inside `run_build`:

```python
            engine_scenes = []
            plan_scenes = []
            for scene in episode.scenes:
                scene_name = f"scene_{scene.order_index:02d}"
                _, ext = os.path.splitext(scene.asset_object_key)
                local_asset_path = os.path.join(temp_dir, "assets", f"{scene_name}{ext}")
                download_to_path(scene.asset_object_key, local_asset_path)
                engine_scenes.append(
                    EngineScene(name=scene_name, asset=local_asset_path, text=scene.narration_text)
                )
                plan_scenes.append(
                    PlanScene(name=scene_name, text=scene.narration_text, asset=scene.asset_object_key)
                )
            engine_episode = EngineEpisode(
                title=episode.title,
                description=episode.description,
                tags=[t.strip() for t in episode.tags.split(",") if t.strip()],
                scenes=engine_scenes,
            )
            plan = ProductionPlan(
                title=engine_episode.title,
                description=engine_episode.description,
                tags=engine_episode.tags,
                sections=[PlanSection(id="main", title=episode.title, scenes=plan_scenes)],
            )
            plan.validate()
```

Delete the import line entirely (line 17) — `PlanScene`/`PlanSection`/`ProductionPlan` will have no remaining references in this file once the block below is replaced. Add this import instead, grouped with the other `from .xxx import` lines (alongside `from .object_storage import upload_bytes`):

```python
from .production_plan_builder import build_plan_from_db_episode
```

Replace the block above with:

```python
            engine_scenes = []
            for scene in episode.scenes:
                scene_name = f"scene_{scene.order_index:02d}"
                _, ext = os.path.splitext(scene.asset_object_key)
                local_asset_path = os.path.join(temp_dir, "assets", f"{scene_name}{ext}")
                download_to_path(scene.asset_object_key, local_asset_path)
                engine_scenes.append(
                    EngineScene(name=scene_name, asset=local_asset_path, text=scene.narration_text)
                )
            engine_episode = EngineEpisode(
                title=episode.title,
                description=episode.description,
                tags=[t.strip() for t in episode.tags.split(",") if t.strip()],
                scenes=engine_scenes,
            )
            plan = build_plan_from_db_episode(episode)
            plan.validate()
```

(`plan_scenes` and its per-scene `.append(...)` are removed entirely — `build_plan_from_db_episode` reconstructs the same data independently from `episode.scenes`, so keeping the parallel list would just be dead code. The `plan.validate()` call and everything after it, including the `plan_key`/`upload_bytes` block, stays exactly as it is — it only uses the `plan` variable, not the `PlanScene`/`PlanSection`/`ProductionPlan` class names.)

- [ ] **Step 6: Run the full backend test suite**

Run: `python -m pytest tests/saas/test_tasks.py tests/saas/test_build_plan.py tests/saas/test_production_plan_builder.py -q`
Expected: all pass — `run_build`'s uploaded `production_plan.json` content is byte-identical to before (same section id `"main"`, same scene naming, same field values), since `build_plan_from_db_episode` reproduces exactly the code it replaced.

Run: `python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add saas/production_plan_builder.py saas/tasks.py tests/saas/test_production_plan_builder.py
git commit -m "refactor: extract build_plan_from_db_episode from run_build

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: LLM critic (`saas/ai/script_quality_critic.py`)

**Files:**
- Create: `saas/ai/script_quality_critic.py`
- Test: `tests/saas/test_script_quality_critic.py`

**Interfaces:**
- Consumes: `ProductionPlan`, `QualityFlag` from `agent_video.production_plan` / `agent_video.script_quality`; `SceneCritique` from `agent_video.script_quality`; `AIError`, `generate_json` from `saas.ai.client`.
- Produces: `critique_script(plan: ProductionPlan, flags: list[QualityFlag], language: str) -> list[SceneCritique]`. Task 5's CLI script calls this.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_script_quality_critic.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/saas/test_script_quality_critic.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saas.ai.script_quality_critic'`

- [ ] **Step 3: Write the implementation**

Create `saas/ai/script_quality_critic.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/saas/test_script_quality_critic.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add saas/ai/script_quality_critic.py tests/saas/test_script_quality_critic.py
git commit -m "feat: add whole-episode LLM naturalness critic

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: CLI driver `scripts/check_script_quality.py`

**Files:**
- Create: `scripts/check_script_quality.py`

**Interfaces:**
- Consumes: `build_plan_from_db_episode` (Task 3); `check_plan`, `render_quality_report` (Tasks 1-2); `critique_script` (Task 4); `saas.db.init_session_factory`; `saas.models.Episode`.
- Produces: nothing importable — this is a standalone script, matching `scripts/compare_voice_style_and_music.py`'s convention (not unit-tested, per spec).

- [ ] **Step 1: Write the script**

Create `scripts/check_script_quality.py`:

```python
"""Run the deterministic + LLM script-quality check against an existing SaaS episode.

Usage (from D:\\Video\\agent_video, with .env loaded and ANTHROPIC_API_KEY + DATABASE_URL set):
    py scripts/check_script_quality.py <episode_id> [--output PATH]

Writes zero changes to the DB, the plan, or the script — this only produces a report.
Default output: script_quality_ep<episode_id>.md in the current directory.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from agent_video.script_quality import check_plan, render_quality_report  # noqa: E402
from saas.ai.script_quality_critic import critique_script  # noqa: E402
from saas.db import init_session_factory  # noqa: E402
from saas.models import Episode  # noqa: E402
from saas.production_plan_builder import build_plan_from_db_episode  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_id", type=int)
    parser.add_argument("--output", default=None)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    output_path = args.output or f"script_quality_ep{args.episode_id}.md"

    session_factory = init_session_factory()
    db = session_factory()
    try:
        episode = db.query(Episode).filter_by(id=args.episode_id).one()
        plan = build_plan_from_db_episode(episode)
        plan.validate()
    finally:
        db.close()

    print(f"Checking {len(plan.flatten_scenes())} scenes...")
    flags = check_plan(plan)
    print(f"Rule checker: {len(flags)} flag(s) across {len({f.scene_name for f in flags})} scene(s)")

    print("Running LLM critique pass (one call for the whole episode)...")
    critiques = critique_script(plan, flags, language=args.language)
    print(f"LLM critic: {len(critiques)} scene(s) with issues")

    report = render_quality_report(plan, flags, critiques)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nWrote report: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script imports cleanly**

Run: `python -c "import ast; ast.parse(open('scripts/check_script_quality.py', encoding='utf-8').read())"`
Expected: no output (syntax is valid; this does not execute the script or require a live DB/API key)

- [ ] **Step 3: Commit**

```bash
git add scripts/check_script_quality.py
git commit -m "feat: add check_script_quality.py CLI driver

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
