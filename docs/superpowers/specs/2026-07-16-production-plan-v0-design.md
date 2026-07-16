# ProductionPlan v0 — Design

Date: 2026-07-16
Status: Approved in principle by user ("cứ tiếp tục implement, tôi sẽ review sau" — design decisions resolved from the two strategy documents discussed 2026-07-15/16; user reviews this spec together with the implementation).

## Problem

The renderer's input today is whatever each call site hands it: the CLI parses `script.md`
into an `Episode` and feeds it to the engine; the SaaS build task assembles an
`EngineEpisode` from DB rows inline. There is no canonical, persisted representation of
"what this episode's build consists of". Consequences:

- No reproducibility artifact: a rendered MP4 cannot be traced back to a structured input.
- The planned AI authoring path has no schema to target — it would have to emit markdown
  and re-parse it.
- The agreed roadmap (sections, per-section music regions, voice direction) has no place
  to live: `Scene = {name, asset, text}` is the entire data model.

## Goals (v0 — deliberately minimal)

1. One canonical structure, `ProductionPlan`, defined in the engine, with JSON
   round-trip and validation. It is the boundary between authoring and rendering.
2. Markdown becomes an input adapter: `script.md → parse → ProductionPlan → build`.
   The DB path likewise: `DB rows → ProductionPlan → build`.
3. Every build persists `production_plan.json` (CLI: in the episode dir; SaaS: uploaded
   next to the output in object storage) — the reproducibility artifact.
4. Sections exist in the schema and in the markdown format, so the next roadmap steps
   (music regions, voice direction per section) have a home. The renderer does NOT yet
   use section data — scenes are flattened for rendering exactly as today.
5. No field exists in the schema that no code writes. "Fields for later" are forbidden.

## Non-goals (deferred)

- Changing renderer internals (`build_scene_clip`, `build_episode` signatures unchanged).
- Music regions / per-section audio behavior (next roadmap step, after EP1 review).
- DB schema changes (`saas/models.py` untouched; DB scenes map to one default section).
- AI generating plans directly (future adapter; this v0 gives it the target schema).
- Plan versioning/history, dependency graph.

## Design

### Approaches considered

- **A (chosen): plan as engine dataclasses + adapters at call sites.** Renderer internals
  unchanged; both call sites construct a plan, validate, persist, then derive the scene
  list from it. Smallest diff that establishes the boundary and the artifact.
- B: refactor the renderer to consume the plan directly. Bigger diff across
  image_builder/video_builder for zero immediate behavior gain — rejected for v0.
- C: JSON Schema file + `jsonschema` validation. New dependency and indirection for a
  schema this small — rejected; hand-rolled `validate()` with precise error messages.

### Schema (version "0.1")

```json
{
  "version": "0.1",
  "episode": {
    "title": "What Happens In The First 24 Hours...",
    "description": "",
    "tags": ["zombie", "what-if"]
  },
  "sections": [
    {
      "id": "first-signs",
      "title": "The First Signs",
      "mood": "suspense",
      "intensity": 0.35,
      "music_profile": "suspense-low",
      "scenes": [
        { "name": "scene_01", "text": "At first, nobody...", "asset": "empty_street.png" }
      ]
    }
  ]
}
```

- `mood`, `intensity`, `music_profile` are optional (`null` when absent). They are
  written by the markdown adapter when the author provides them; nothing reads them yet
  (the music-regions step will). This is the one deliberate exception to "no unused
  fields": the section metadata IS the point of v0 per the agreed strategy — authored
  today, consumed next step.
- `scenes[].asset` is an authoring-side reference: a filename for the CLI (resolved
  against `assets/` + `assets_common/` exactly as today), an S3 object key for SaaS.
  The plan does not know about local paths; each call site resolves references.

### Engine module `agent_video/production_plan.py`

- `PLAN_VERSION = "0.1"`.
- Dataclasses: `PlanScene(name, text, asset)`,
  `PlanSection(id, title, scenes, mood=None, intensity=None, music_profile=None)`,
  `ProductionPlan(title, description, tags, sections, version=PLAN_VERSION)`.
- `PlanValidationError(ValueError)`.
- `ProductionPlan.validate()`: at least one section; every section has ≥1 scene; scene
  `name`/`text`/`asset` non-empty; scene names unique across the whole plan; section ids
  non-empty and unique; `intensity`, when present, in [0, 1]. Error messages name the
  offending section/scene.
- `to_dict()` / `from_dict(data)` (from_dict validates), `write_plan(plan, path)` /
  `load_plan(path)` (UTF-8 JSON, `ensure_ascii=False`, indent 2).
- `flatten_scenes() -> list[PlanScene]` — document order, what the renderer loop consumes.
- `plan_from_episode(episode: Episode) -> ProductionPlan` — compiler from the parsed
  markdown structure (below).

### Markdown adapter (script_parser)

Backward-compatible extension of `script.md`:

```markdown
title: ...
description: ...
tags: a, b

## SECTION: The First Signs
mood: suspense
intensity: 0.35
music: suspense-low

## scene_01
asset: empty_street.png
text: At first, nobody would understand what was happening.
```

- A line matching `^##\s+SECTION:\s*(.+)$` starts a new section. Metadata lines
  (`mood:`, `intensity:`, `music:`) may follow before the first scene of that section.
  Section id = slugified title.
- Scene blocks (`## scene_xx`) are unchanged and belong to the most recent section.
- A script with no SECTION headers (all existing scripts) compiles to a single section
  `{id: "main", title: <episode title>}` with no mood/intensity/music — output identical
  to today.
- Parse errors for: SECTION with no scenes, invalid `intensity` (non-float or out of
  range), unknown metadata keys are ignored (consistent with the parser's current
  tolerance of unknown frontmatter keys).
- `Episode` dataclass gains `sections: list[ScriptSection]`
  (`ScriptSection(title, mood, intensity, music, scenes)`); `Episode.scenes` remains and
  stays flat (all existing consumers unchanged).

### CLI integration (`cmd_build`)

After parsing: `plan = plan_from_episode(episode)`, `plan.validate()`,
`write_plan(plan, <video_dir>/production_plan.json)`. The TTS/clip loops iterate
`plan.flatten_scenes()` instead of `episode.scenes` (same order, same values — behavior
identical). Manifest/asset resolution unchanged.

### SaaS integration (`run_build`)

Build `ProductionPlan` from DB rows: one section `{id: "main", title: episode.title}`,
scenes in `order_index` order with `asset` = the scene's object key. `plan.validate()`,
write `production_plan.json` into the temp dir, and upload it to
`episodes/{episode_id}/production_plan.json` via `upload_bytes` (persisted artifact —
the temp dir is deleted after the build). The engine-scene construction then derives
from the plan's flattened scenes (name/text from plan; local asset path from the
existing per-scene download map).

### Error handling

- Plan validation failure fails the build with the validation message (CLI: printed,
  non-zero path as with parse errors; SaaS: job failed with error_message) — an invalid
  plan must never render.
- Plan JSON write/upload failures: CLI write failure fails the build (local disk broken
  is fatal anyway); SaaS upload failure is logged as a warning and does not fail the
  build (artifact is valuable but not worth failing a finished render for).

## Testing

- Unit `tests/test_production_plan.py`: round-trip dict/JSON equality; validation errors
  for each rule (empty sections, empty scenes, blank fields, duplicate names/ids,
  intensity out of range) with message content asserted; flatten order; version constant
  present in output.
- Parser `tests/test_script_parser.py` (append): sectionless script → one "main" section,
  flat scenes unchanged; sectioned script → correct section metadata + scene grouping;
  SECTION with no scenes → ScriptParseError; bad intensity → ScriptParseError.
- CLI `tests/test_cli.py` (append): build writes `production_plan.json` matching the
  script; build output path unchanged.
- SaaS `tests/saas/test_tasks.py`-style (new file `tests/saas/test_build_plan.py`):
  successful build uploads `episodes/{id}/production_plan.json` whose scenes match the
  DB rows; plan upload failure does not fail the job.

## Success criteria

- Both pipelines persist a valid `production_plan.json` for every successful build.
- All pre-existing scripts and DB episodes build with byte-identical behavior.
- Full test suite passes.
