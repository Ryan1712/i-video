# Script Quality v0 — Design

Date: 2026-07-16
Status: Approved in principle by user ("cứ tiếp tục implement, tôi sẽ review sau" — this spec
is a deliberately cut-down version of a much larger multi-agent "Script Quality Pipeline"
proposal the user relayed from an external analysis; user reviews this spec together with
the implementation).

## Problem

A textual critique of EP1 v3's narration (37 scenes, episode 6) identified two independent
issues:

1. **Formulaic AI prose**: recurring cliché constructions ("the question was no longer X, it
   was Y", "from that moment on...", "like never before") and a high density of
   rhetorical-question / dramatic-fragment endings — a known LLM writing tell, confirmed by
   reading `saas/ai/script_generation.py`'s system prompt, which currently has zero
   naturalness or structure constraints.
2. **Genre mismatch**: the episode splices a chronological survival narrative (scenes 1-30),
   a "Mistake number one/two/three" listicle (scenes 31-34), and a cinematic cliffhanger
   (scenes 35-37) — three different video formats stitched together.

The critique proposed an elaborate multi-agent pipeline (Story Planner → Draft Writer →
Naturalness Critic → Selective Rewriter → Spoken-language Validator, plus a `NarrationProfile`
schema, a few-shot style-reference retrieval system, per-series learned preferences, and
eventual fine-tuning). That is far more than a solo project with zero validated episodes
needs today.

## Goals (v0 — deliberately minimal)

1. Surface the two issue classes above as a **human-readable report**, so the user can decide
   what to actually rewrite in EP1 without re-reading all 37 scenes hunting for problems.
2. Catch the cheap, deterministic 80%: known cliché phrases, structural patterns, overlong
   sentences, repeated intensifier words — for free, with regex, no AI cost.
3. Catch what regex can't: abstract commentary, genre-shift, tonal issues — with **one**
   whole-episode LLM call that reads the deterministic flags as hints and returns per-scene
   issues with suggested rewrites.
4. Zero write access to the script, plan, or DB. This tool only produces a report; a human
   decides what to change and edits `script.md` / regenerates via the existing AI script
   endpoints themselves.
5. Reuse `ProductionPlan` (built 2026-07-16) as the input structure — the natural next
   consumer of that artifact, not a parallel data model.

## Non-goals (deferred — explicit backlog, not silently dropped)

- `NarrationProfile` / `ScriptPlan` schemas with tunable numeric style knobs.
- Few-shot style-reference retrieval, multiple rewrite candidates + a ranker model.
- Multi-tier (scene/section/episode) critics; a single episode-level pass is enough at this
  scale (37 scenes, ~1200 words).
- Auto-apply of any suggestion; per-series learned-preference feedback loop; fine-tuning.
- A web UI or API endpoint — this is an internal tool run from the command line against a
  DB-backed episode, matching the existing `scripts/compare_tts_vi.py`-style convention.

## Design

### Approaches considered

- **A (chosen): rule-check → single batched LLM critique → markdown report.** One API call
  regardless of episode length, rules feed the critic as hints (not a hard gate), engine/saas
  boundary preserved (rules are pure Python in `agent_video/`, the LLM call lives in `saas/`).
- B: critic call per flagged scene only (skip clean scenes). Rejected — misses issues in
  scenes the regex didn't flag (e.g. "Everyone tried to leave at once" style abstract
  commentary has no fixed cliché phrase), and at this episode size batching the whole
  narration into one call is barely more expensive than N small calls.
- C: 3 rewrite candidates + a separate ranker call. Rejected for v0 — doubles/triples LLM
  cost and adds a ranking problem for zero validated benefit; a single suggestion is enough
  for a human to accept, edit, or ignore.

### `agent_video/script_quality.py` (engine — pure Python, no AI/DB dependency)

```python
@dataclass
class QualityFlag:
    scene_name: str
    rule_id: str
    severity: int  # 1-3, informational only in v0 (displayed per flag, not used for gating or ordering — the report follows plan/scene order)
    matched_text: str
    reason: str

@dataclass
class Rule:
    id: str
    pattern: re.Pattern
    severity: int
    reason: str

RULES: list[Rule]  # see "Rule set" below

@dataclass
class SceneCritique:
    scene_name: str
    issue: str
    reason: str
    rewrite_suggestion: str
    severity: int

def check_plan(plan: ProductionPlan) -> list[QualityFlag]: ...
```

- `check_plan` iterates `plan.flatten_scenes()`; for each scene applies every per-scene regex
  rule (each match → one `QualityFlag`), plus one plan-wide rule (repeated intensifier words —
  flags the 2nd+ occurrence of any watched word across the whole episode).
- Rules are pure-function regex matches over `scene.text` — no state beyond the plan-wide
  word-repetition counter.

**Rule set (v0, curated from the critique's concrete examples):**

| id | pattern (case-insensitive) | severity | reason |
|---|---|---|---|
| `cliche_question_no_longer` | `the question was no longer` | 3 | Formulaic dramatic contrast |
| `cliche_from_that_moment` | `from that moment (on\|forward)` | 2 | Generic turning-point narration |
| `cliche_little_did` | `little did \w+ know` | 3 | Cliché omniscient foreshadowing |
| `cliche_whole_new_level` | `(a )?whole new level` | 2 | Generic intensifier |
| `cliche_like_never_before` | `like (never\|nothing) before` | 2 | Generic dramatic exaggeration |
| `cliche_everything_about_to_change` | `everything (was\|is) about to change` | 2 | Generic dramatic setup |
| `cliche_officially` | `officially (began\|started)` | 2 | Narrator declares a turning point instead of showing it |
| `structural_not_x_not_y_but_z` | `not\s+\w[^.]*\.\s*not\s+\w[^.]*\.\s*but\b` | 2 | Repeated triplet-contrast sentence structure |
| `structural_no_x_no_y` | `\bno\s+[^.!?]+[.!?]\s+no\s+[^.!?]+[.!?]` | 1 | Repeated sentence-fragment structure (multi-word "No X. No Y." pairs, e.g. "No further details. No explanation.") |
| `long_sentence` | (not regex — split `scene.text` on `[.!?]`, flag any sentence > 28 words) | 1 | Hard to speak aloud / read as one breath |
| `rhetorical_ending` | scene text ends with `?` | 1 | Rhetorical-question ending (fine occasionally, a tell in density) |
| `repeated_intensifier` | (plan-wide, word-boundary match) any of `panic, chaos, suddenly, completely, nightmare, terrifying, desperate, truly` | 1 | Same intensifier reused across the episode instead of varying description — flags every scene from the word's 2nd occurrence onward (the 1st use is unflagged) |

Rules are data, not hardcoded logic — adding one later is adding a table row, matching the
"anti-pattern library" idea from the critique without building the surrounding pipeline.

### `saas/production_plan_builder.py`

```python
def build_plan_from_db_episode(episode: Episode) -> ProductionPlan: ...
```

Extracts the plan-construction block already inline in `saas/tasks.py::run_build` (one
section `"main"`, one `PlanScene` per `Scene` row: `name=f"scene_{order_index:02d}"`,
`text=narration_text`, `asset=asset_object_key`) into a reusable function. `run_build` is
refactored to call it (behavior-identical — `episode.scenes` is already DB-ordered by
`order_index`, per the `relationship(..., order_by="Scene.order_index")` in `models.py`).
This lets the quality-check script build a plan for an **existing** episode without
downloading assets, running TTS, or rendering anything — it only reads `narration_text`.

### `saas/ai/script_quality_critic.py`

```python
def critique_script(plan: ProductionPlan, flags: list[QualityFlag], language: str) -> list[SceneCritique]: ...
```

- `SceneCritique` (defined in `agent_video/script_quality.py`, imported here):
  `scene_name: str, issue: str, reason: str, rewrite_suggestion: str, severity: int`.
- One `generate_json` call (reusing `saas/ai/client.py`, same pattern as
  `script_analysis.py`). The prompt includes: the full narration in scene order (name +
  text), and the rule-flag hints grouped by scene ("scene_013: cliche_officially — matched
  'officially began'"). The model is instructed to read the whole episode for tone/genre
  consistency and flag scenes with real issues — not necessarily only the hinted ones —
  returning `{"critiques": [{"scene_name": ..., "issue": ..., "reason": ..., "rewrite_suggestion": ..., "severity": 1-3}]}`.
  A clean scene simply doesn't appear in the list.
- Parsing validates the required keys per critique item and raises `AIError` on a malformed
  reply, mirroring `script_analysis.py`'s validation style exactly.

### `agent_video/script_quality.py` — report rendering

```python
def render_quality_report(plan: ProductionPlan, flags: list[QualityFlag], critiques: list[SceneCritique]) -> str: ...
```

Pure formatting function (no I/O). One markdown section per scene that has any flag or
critique (clean scenes omitted entirely — the point is to shrink the review surface, not
reproduce the full script). Each section: scene name, original text, rule flags (id +
matched text), LLM issue + reason + rewrite suggestion, and a
`- [ ] Áp dụng gợi ý trên` checkbox line — matching the checkbox-review pattern already
familiar from `review_ep1_en_v3.md`. A summary line at the top: total scenes, scenes flagged.

### `scripts/check_script_quality.py`

CLI driver, matching the existing `scripts/*.py` convention (untested one-off tools calling
into the SaaS DB/AI layer directly):

```
python scripts/check_script_quality.py <episode_id> [--output PATH]
```

Loads the episode via `saas.db`, calls `build_plan_from_db_episode`, `check_plan`,
`critique_script`, `render_quality_report`, writes the result to `--output` (default:
`script_quality_ep<id>.md` in the current directory). Requires `ANTHROPIC_API_KEY` and
`DATABASE_URL` in the environment exactly like the existing `scripts/compare_*.py` tools.

## Testing

- `tests/test_script_quality.py`: one positive + one negative test per rule pattern; the
  plan-wide `repeated_intensifier` rule tested across multiple scenes; `render_quality_report`
  output format checked (scene with no flags/critiques omitted; summary counts correct).
- `tests/saas/test_script_quality_critic.py`: mocks `generate_json`, asserts the prompt
  includes all scene texts and the flag hints; asserts malformed replies (missing key) raise
  `AIError`; asserts a well-formed reply converts to `SceneCritique` objects correctly.
- `tests/saas/test_production_plan_builder.py`: `build_plan_from_db_episode` produces the
  expected single-section plan from `Episode`/`Scene` rows (asset = object key, not a local
  path). `saas/tasks.py` refactored to call it — pre-existing `tests/saas/test_build_plan.py`
  and `tests/saas/test_tasks.py` must pass unchanged (behavior-identical extraction).
- `scripts/check_script_quality.py` is not unit-tested, consistent with the existing
  untested `scripts/*.py` convention in this repo.

## Success criteria

- Running the script against episode 6 (EP1 v3, 37 scenes) produces a report the user can
  read start to finish and know exactly which scenes to rewrite and why, without re-reading
  the full 9-minute narration.
- Full test suite passes; `run_build` behavior is provably unchanged.
