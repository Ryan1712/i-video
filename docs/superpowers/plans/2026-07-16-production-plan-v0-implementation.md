# ProductionPlan v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `ProductionPlan` as the canonical, validated, persisted structure between authoring (markdown / DB rows) and the renderer, with sections in the schema and in `script.md`.

**Architecture:** New engine module `agent_video/production_plan.py` owns the dataclasses, validation, and JSON round-trip. `script_parser` gains backward-compatible `## SECTION:` support and remains the markdown adapter; `plan_from_episode` compiles its output into a plan. Both call sites (CLI `cmd_build`, SaaS `run_build`) construct + validate + persist the plan, then drive the existing render loops from `plan.flatten_scenes()`. Renderer internals (`build_scene_clip`, `build_episode`) are untouched.

**Tech Stack:** Python 3.12, dataclasses, pytest, moto (`@mock_aws`) for S3 tests. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-production-plan-v0-design.md`

## Global Constraints

- Run tests from repo root `d:\Video\agent_video` with `python -m pytest tests/ -q`. Suite currently passes with 278 tests — all must still pass.
- Plan schema version string: `PLAN_VERSION = "0.1"`.
- No schema field that no code writes (mood/intensity/music_profile are written by the markdown adapter — allowed by spec).
- Scripts without `## SECTION:` headers must build with behavior identical to today.
- `saas/models.py` must NOT change.
- All commits on branch `production-plan-v0`, end commit messages with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Engine module `production_plan.py` — dataclasses, validation, JSON round-trip

**Files:**
- Create: `agent_video/production_plan.py`
- Test: `tests/test_production_plan.py`

**Interfaces:**
- Produces (later tasks import all of these from `agent_video.production_plan`):
  - `PLAN_VERSION: str = "0.1"`
  - `class PlanValidationError(ValueError)`
  - `@dataclass PlanScene(name: str, text: str, asset: str)`
  - `@dataclass PlanSection(id: str, title: str, scenes: list[PlanScene], mood: str | None = None, intensity: float | None = None, music_profile: str | None = None)`
  - `@dataclass ProductionPlan(title: str, description: str, tags: list[str], sections: list[PlanSection], version: str = PLAN_VERSION)` with methods `validate() -> None`, `to_dict() -> dict`, `flatten_scenes() -> list[PlanScene]`, classmethod `from_dict(data: dict) -> ProductionPlan`
  - `write_plan(plan: ProductionPlan, path: str) -> None`, `load_plan(path: str) -> ProductionPlan`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_production_plan.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_production_plan.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_video.production_plan'`

- [ ] **Step 3: Write the implementation**

Create `agent_video/production_plan.py`:

```python
"""ProductionPlan v0: the canonical structure between authoring and the renderer."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

PLAN_VERSION = "0.1"


class PlanValidationError(ValueError):
    pass


@dataclass
class PlanScene:
    name: str
    text: str
    asset: str


@dataclass
class PlanSection:
    id: str
    title: str
    scenes: list[PlanScene] = field(default_factory=list)
    mood: str | None = None
    intensity: float | None = None
    music_profile: str | None = None


@dataclass
class ProductionPlan:
    title: str
    description: str
    tags: list[str]
    sections: list[PlanSection]
    version: str = PLAN_VERSION

    def validate(self) -> None:
        if not self.sections:
            raise PlanValidationError("plan has no sections")
        seen_section_ids: set[str] = set()
        seen_scene_names: set[str] = set()
        for section in self.sections:
            if not section.id or not section.id.strip():
                raise PlanValidationError(f"section '{section.title}' has an empty id")
            if section.id in seen_section_ids:
                raise PlanValidationError(f"duplicate section id '{section.id}'")
            seen_section_ids.add(section.id)
            if not section.scenes:
                raise PlanValidationError(f"section '{section.id}' has no scenes")
            if section.intensity is not None and not 0.0 <= section.intensity <= 1.0:
                raise PlanValidationError(
                    f"section '{section.id}' intensity {section.intensity} is outside [0, 1]"
                )
            for scene in section.scenes:
                for field_name in ("name", "text", "asset"):
                    value = getattr(scene, field_name)
                    if not value or not value.strip():
                        raise PlanValidationError(
                            f"scene '{scene.name}' in section '{section.id}' has an empty '{field_name}'"
                        )
                if scene.name in seen_scene_names:
                    raise PlanValidationError(f"duplicate scene name '{scene.name}'")
                seen_scene_names.add(scene.name)

    def flatten_scenes(self) -> list[PlanScene]:
        return [scene for section in self.sections for scene in section.scenes]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "episode": {
                "title": self.title,
                "description": self.description,
                "tags": list(self.tags),
            },
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "mood": section.mood,
                    "intensity": section.intensity,
                    "music_profile": section.music_profile,
                    "scenes": [
                        {"name": scene.name, "text": scene.text, "asset": scene.asset}
                        for scene in section.scenes
                    ],
                }
                for section in self.sections
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProductionPlan":
        try:
            episode = data["episode"]
            sections = [
                PlanSection(
                    id=raw["id"],
                    title=raw["title"],
                    mood=raw.get("mood"),
                    intensity=raw.get("intensity"),
                    music_profile=raw.get("music_profile"),
                    scenes=[
                        PlanScene(name=s["name"], text=s["text"], asset=s["asset"])
                        for s in raw["scenes"]
                    ],
                )
                for raw in data["sections"]
            ]
            plan = cls(
                title=episode["title"],
                description=episode.get("description", ""),
                tags=list(episode.get("tags", [])),
                sections=sections,
                version=data.get("version", PLAN_VERSION),
            )
        except (KeyError, TypeError) as exc:
            raise PlanValidationError(f"malformed production plan: {exc!r}") from exc
        plan.validate()
        return plan


def write_plan(plan: ProductionPlan, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, indent=2, ensure_ascii=False)


def load_plan(path: str) -> ProductionPlan:
    with open(path, "r", encoding="utf-8") as f:
        return ProductionPlan.from_dict(json.load(f))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_production_plan.py -q`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add agent_video/production_plan.py tests/test_production_plan.py
git commit -m "feat: add ProductionPlan v0 schema module

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: script_parser SECTION support + plan compiler

**Files:**
- Modify: `agent_video/script_parser.py` (add `ScriptSection`, section-aware parse loop, `slugify` moved here)
- Modify: `agent_video/cli.py` (remove local `slugify`, import it from script_parser)
- Modify: `agent_video/production_plan.py` (append `plan_from_episode`)
- Test: `tests/test_script_parser.py` (append), `tests/test_production_plan.py` (append)

**Interfaces:**
- Consumes: Task 1's dataclasses.
- Produces:
  - `agent_video.script_parser.slugify(title: str) -> str` (moved verbatim from cli.py; `agent_video.cli.slugify` keeps working via import re-export)
  - `@dataclass ScriptSection(title: str, mood: str | None = None, intensity: float | None = None, music: str | None = None, scenes: list[Scene] = ...)` in script_parser
  - `Episode` gains field `sections: list[ScriptSection] = field(default_factory=list)`; `parse_script` always populates it (implicit single section when no SECTION headers); `Episode.scenes` stays flat and unchanged.
  - `agent_video.production_plan.plan_from_episode(episode) -> ProductionPlan` (Task 3/4 call this).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_script_parser.py`:

```python
def _write(tmp_path, content):
    path = str(tmp_path / "script.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


SECTIONED_SCRIPT = """title: Zombie EP1
description: d
tags: zombie

## SECTION: The First Signs
mood: suspense
intensity: 0.35
music: suspense-low

## scene_01
asset: street.png
text: At first, nobody knew.

## scene_02
asset: news.png
text: The news was confusing.

## SECTION: The Collapse
mood: panic

## scene_03
asset: hospital.png
text: Hospitals overflowed.
"""


def test_sectionless_script_gets_one_implicit_section(tmp_path):
    path = _write(tmp_path, "title: T\n\n## scene_01\nasset: a.png\ntext: hi\n")
    episode = parse_script(path)
    assert len(episode.sections) == 1
    section = episode.sections[0]
    assert section.title == "T"
    assert section.mood is None and section.intensity is None and section.music is None
    assert [s.name for s in section.scenes] == ["scene_01"]
    assert [s.name for s in episode.scenes] == ["scene_01"]


def test_sectioned_script_parses_sections_and_metadata(tmp_path):
    episode = parse_script(_write(tmp_path, SECTIONED_SCRIPT))
    assert [s.title for s in episode.sections] == ["The First Signs", "The Collapse"]
    first, second = episode.sections
    assert first.mood == "suspense"
    assert first.intensity == 0.35
    assert first.music == "suspense-low"
    assert [s.name for s in first.scenes] == ["scene_01", "scene_02"]
    assert second.mood == "panic"
    assert second.intensity is None and second.music is None
    assert [s.name for s in second.scenes] == ["scene_03"]
    # flat list unchanged for existing consumers
    assert [s.name for s in episode.scenes] == ["scene_01", "scene_02", "scene_03"]


def test_section_with_no_scenes_rejected(tmp_path):
    content = "title: T\n\n## SECTION: Empty\nmood: dark\n\n## SECTION: Real\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match="section 'Empty' has no scenes"):
        parse_script(_write(tmp_path, content))


def test_trailing_section_with_no_scenes_rejected(tmp_path):
    content = "title: T\n\n## scene_01\nasset: a.png\ntext: hi\n\n## SECTION: Tail\nmood: dark\n"
    with pytest.raises(ScriptParseError, match="section 'Tail' has no scenes"):
        parse_script(_write(tmp_path, content))


def test_invalid_intensity_rejected(tmp_path):
    content = "title: T\n\n## SECTION: A\nintensity: high\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match="invalid intensity 'high'"):
        parse_script(_write(tmp_path, content))


def test_out_of_range_intensity_rejected(tmp_path):
    content = "title: T\n\n## SECTION: A\nintensity: 1.5\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match=r"intensity 1.5 outside \[0, 1\]"):
        parse_script(_write(tmp_path, content))


def test_section_metadata_does_not_leak_into_scene_fields(tmp_path):
    episode = parse_script(_write(tmp_path, SECTIONED_SCRIPT))
    assert episode.scenes[0].text == "At first, nobody knew."


def test_slugify_moved_to_script_parser():
    from agent_video.script_parser import slugify

    assert slugify("The First Signs!") == "the-first-signs"
```

(The file already imports `parse_script`, `ScriptParseError`, and `pytest` — check its
header first; add any missing import at the top rather than mid-file.)

Append to `tests/test_production_plan.py`:

```python
from agent_video.production_plan import plan_from_episode
from agent_video.script_parser import Episode, Scene, ScriptSection


def test_plan_from_sectionless_episode():
    scenes = [Scene(name="scene_01", asset="a.png", text="hi")]
    episode = Episode(
        title="Test", description="d", tags=["x"], scenes=scenes,
        sections=[ScriptSection(title="Test", scenes=scenes)],
    )
    plan = plan_from_episode(episode)
    plan.validate()
    assert plan.title == "Test"
    assert [s.id for s in plan.sections] == ["test"]
    assert plan.sections[0].mood is None
    assert [s.name for s in plan.flatten_scenes()] == ["scene_01"]


def test_plan_from_sectioned_episode_carries_metadata():
    s1 = [Scene(name="scene_01", asset="a.png", text="one")]
    s2 = [Scene(name="scene_02", asset="b.png", text="two")]
    episode = Episode(
        title="EP", description="", tags=[], scenes=s1 + s2,
        sections=[
            ScriptSection(title="The First Signs", mood="suspense", intensity=0.35,
                          music="suspense-low", scenes=s1),
            ScriptSection(title="The Collapse", mood="panic", scenes=s2),
        ],
    )
    plan = plan_from_episode(episode)
    plan.validate()
    assert [s.id for s in plan.sections] == ["the-first-signs", "the-collapse"]
    assert plan.sections[0].music_profile == "suspense-low"
    assert plan.sections[0].intensity == 0.35
    assert plan.sections[1].mood == "panic"


def test_plan_from_episode_deduplicates_and_falls_back_ids():
    s1 = [Scene(name="scene_01", asset="a.png", text="one")]
    s2 = [Scene(name="scene_02", asset="b.png", text="two")]
    s3 = [Scene(name="scene_03", asset="c.png", text="three")]
    episode = Episode(
        title="EP", description="", tags=[], scenes=s1 + s2 + s3,
        sections=[
            ScriptSection(title="!!!", scenes=s1),       # slug empty -> section-1
            ScriptSection(title="Same", scenes=s2),
            ScriptSection(title="Same", scenes=s3),      # duplicate -> same-2
        ],
    )
    plan = plan_from_episode(episode)
    plan.validate()
    assert [s.id for s in plan.sections] == ["section-1", "same", "same-2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_script_parser.py tests/test_production_plan.py -q`
Expected: FAIL — new parser tests fail (`Episode` has no `sections`; `slugify` import error; `plan_from_episode` import error). Pre-existing tests still pass.

- [ ] **Step 3: Implement the parser changes**

In `agent_video/script_parser.py`:

Add after the `Scene` dataclass:

```python
@dataclass
class ScriptSection:
    title: str
    mood: str | None = None
    intensity: float | None = None
    music: str | None = None
    scenes: list[Scene] = field(default_factory=list)
```

Change `Episode` to:

```python
@dataclass
class Episode:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    sections: list[ScriptSection] = field(default_factory=list)
```

Add after `_FIELD_RE`:

```python
_SECTION_HEADER_RE = re.compile(r"^##\s+SECTION:\s*(.+?)\s*$")
_SECTION_META_KEYS = ("mood", "intensity", "music")


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug
```

In `parse_script`, change the frontmatter split so a SECTION header also ends the
frontmatter (currently only scene headers do):

```python
    first_scene_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _SCENE_HEADER_RE.match(stripped) or _SECTION_HEADER_RE.match(stripped):
            first_scene_idx = i
            break
```

(the error message for "no scene blocks found" stays as-is).

Replace the scene-block parsing loop (everything from `# Parse scene blocks.` to the
final `return Episode(...)`) with:

```python
    # Parse section and scene blocks.
    sections: list[ScriptSection] = []
    scenes: list[Scene] = []
    current_section: ScriptSection | None = None
    current_name = None
    current_fields: dict[str, str] = {}

    def _flush_scene():
        if current_name is None:
            return
        if "asset" not in current_fields:
            raise ScriptParseError(
                f"{path}: scene '{current_name}' is missing required field 'asset'"
            )
        if "text" not in current_fields or not current_fields["text"].strip():
            raise ScriptParseError(
                f"{path}: scene '{current_name}' is missing required field 'text'"
            )
        scene = Scene(
            name=current_name,
            asset=current_fields["asset"].strip(),
            text=current_fields["text"].strip(),
        )
        scenes.append(scene)
        current_section.scenes.append(scene)

    def _set_section_meta(section: ScriptSection, key: str, value: str) -> None:
        if key == "intensity":
            try:
                parsed = float(value)
            except ValueError:
                raise ScriptParseError(
                    f"{path}: section '{section.title}' has invalid intensity '{value}'"
                ) from None
            if not 0.0 <= parsed <= 1.0:
                raise ScriptParseError(
                    f"{path}: section '{section.title}' intensity {parsed} outside [0, 1]"
                )
            section.intensity = parsed
        elif key == "mood":
            section.mood = value
        else:
            section.music = value

    for line in lines[first_scene_idx:]:
        stripped = line.strip()

        section_match = _SECTION_HEADER_RE.match(stripped)
        if section_match:
            _flush_scene()
            current_name = None
            current_fields = {}
            if current_section is not None and not current_section.scenes:
                raise ScriptParseError(
                    f"{path}: section '{current_section.title}' has no scenes"
                )
            current_section = ScriptSection(title=section_match.group(1))
            sections.append(current_section)
            continue

        header_match = _SCENE_HEADER_RE.match(stripped)
        if header_match:
            _flush_scene()
            if current_section is None:
                current_section = ScriptSection(title=title)
                sections.append(current_section)
            current_name = header_match.group(1)
            current_fields = {}
            continue

        if not stripped:
            continue
        m = _FIELD_RE.match(stripped)
        if m:
            key, value = m.group(1).lower(), m.group(2).strip()
            if current_name is not None:
                current_fields[key] = value
            elif current_section is not None and key in _SECTION_META_KEYS:
                _set_section_meta(current_section, key, value)
        elif current_name is not None and "text" in current_fields:
            # Allow multi-line narration text continuing on following lines.
            current_fields["text"] += " " + stripped

    _flush_scene()

    if current_section is not None and not current_section.scenes:
        raise ScriptParseError(f"{path}: section '{current_section.title}' has no scenes")
    if not scenes:
        raise ScriptParseError(f"{path}: no valid scenes parsed")

    return Episode(
        title=title, description=description, tags=tags, scenes=scenes, sections=sections
    )
```

In `agent_video/cli.py`: delete the local `slugify` function (lines 30-35) and extend the
existing script_parser import to:

```python
from .script_parser import ScriptParseError, parse_script, slugify
```

- [ ] **Step 4: Implement `plan_from_episode`**

Append to `agent_video/production_plan.py`:

```python
def _section_ids(titles: list[str]) -> list[str]:
    from .script_parser import slugify

    ids: list[str] = []
    for index, title in enumerate(titles):
        base = slugify(title) or f"section-{index + 1}"
        candidate = base
        n = 2
        while candidate in ids:
            candidate = f"{base}-{n}"
            n += 1
        ids.append(candidate)
    return ids


def plan_from_episode(episode) -> ProductionPlan:
    """Compile a parsed script.md Episode into a ProductionPlan."""
    ids = _section_ids([section.title for section in episode.sections])
    sections = [
        PlanSection(
            id=section_id,
            title=section.title,
            mood=section.mood,
            intensity=section.intensity,
            music_profile=section.music,
            scenes=[
                PlanScene(name=scene.name, text=scene.text, asset=scene.asset)
                for scene in section.scenes
            ],
        )
        for section_id, section in zip(ids, episode.sections)
    ]
    return ProductionPlan(
        title=episode.title,
        description=episode.description,
        tags=list(episode.tags),
        sections=sections,
    )
```

(The function-local `slugify` import avoids a module-level cycle: script_parser must
never import production_plan, and production_plan only needs slugify at call time.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_script_parser.py tests/test_production_plan.py tests/test_cli.py -q`
Expected: all pass (including pre-existing parser and CLI tests — `cmd_new` still uses `slugify` via the re-export).

- [ ] **Step 6: Commit**

```bash
git add agent_video/script_parser.py agent_video/cli.py agent_video/production_plan.py tests/test_script_parser.py tests/test_production_plan.py
git commit -m "feat: SECTION support in script.md and plan_from_episode compiler

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI writes and consumes the plan

**Files:**
- Modify: `agent_video/cli.py` (`cmd_build`)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `plan_from_episode`, `write_plan`, `load_plan` from `agent_video.production_plan` (Tasks 1-2).
- Produces: `cmd_build` writes `<video_dir>/production_plan.json` on every build and drives TTS/clip loops from `plan.flatten_scenes()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
SECTIONED_BUILD_SCRIPT = """title: Test
description: d
tags: t

## SECTION: Opening
mood: suspense
intensity: 0.4
music: suspense-low

## scene_01
asset: hero.png
text: hi

## SECTION: Ending
mood: calm

## scene_02
asset: hero.png
text: bye
"""


def test_cmd_build_writes_production_plan(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write(SECTIONED_BUILD_SCRIPT)
    open(os.path.join(ep_dir, "assets", "hero.png"), "wb").close()
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth), \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            result = cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    assert result is not None
    from agent_video.production_plan import load_plan

    plan = load_plan(os.path.join(ep_dir, "production_plan.json"))
    assert plan.title == "Test"
    assert [s.id for s in plan.sections] == ["opening", "ending"]
    assert plan.sections[0].mood == "suspense"
    assert plan.sections[0].intensity == 0.4
    assert plan.sections[0].music_profile == "suspense-low"
    assert [s.name for s in plan.flatten_scenes()] == ["scene_01", "scene_02"]


def test_cmd_build_plan_written_for_sectionless_script(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth), \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    from agent_video.production_plan import load_plan

    plan = load_plan(os.path.join(ep_dir, "production_plan.json"))
    assert len(plan.sections) == 1
    assert [s.name for s in plan.flatten_scenes()] == ["scene_01"]
```

(`_fake_synth` and `_build_ready_episode_dir` already exist in this file from the TTS
cache tests.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q`
Expected: the two new tests FAIL with `FileNotFoundError` for `production_plan.json`; the rest pass.

- [ ] **Step 3: Wire the plan into `cmd_build`**

In `agent_video/cli.py` add the import:

```python
from .production_plan import plan_from_episode, write_plan
```

In `cmd_build`, right after the `manifest["ready"]` check + `print` of Bước 1/4, insert:

```python
    plan = plan_from_episode(episode)
    plan.validate()
    write_plan(plan, os.path.join(video_dir, "production_plan.json"))
    plan_scenes = plan.flatten_scenes()
```

Then change the two loops to iterate plan scenes:
- TTS loop: `for scene in plan_scenes:` (body unchanged — `scene.text`/`scene.name` exist on `PlanScene`).
- Clip loop: `for scene, duration in zip(plan_scenes, durations):` (body unchanged — `scene.asset` is the same filename the manifest lookup uses).
- The two `print` lines that use `len(episode.scenes)` change to `len(plan_scenes)`.

`build_episode(episode, ...)` keeps receiving `episode` (it needs title/description and
per-scene text for subtitles; plan and episode scene lists are identical by construction).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add agent_video/cli.py tests/test_cli.py
git commit -m "feat: CLI build writes and consumes production_plan.json

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: SaaS build task builds and uploads the plan

**Files:**
- Modify: `saas/tasks.py` (`run_build`)
- Test: `tests/saas/test_build_plan.py` (new)

**Interfaces:**
- Consumes: `PlanScene`, `PlanSection`, `ProductionPlan`, `write_plan` from `agent_video.production_plan`; `upload_bytes` from `saas.object_storage`.
- Produces: every successful SaaS build uploads `episodes/{episode_id}/production_plan.json`; plan-upload failure logs a warning and does not fail the job.

- [ ] **Step 1: Write the failing tests**

Create `tests/saas/test_build_plan.py`:

```python
"""SaaS build task persists a ProductionPlan artifact to object storage."""
import json
from unittest.mock import patch

from moto import mock_aws

from saas.models import Episode, Job, Scene, User
from saas.tasks import run_build


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


def _fake_synth(text, out_path, api_key, voice_id, style=0.0):
    with open(out_path, "wb") as f:
        f.write(b"audio:" + text.encode("utf-8"))


def _make_episode(db_session, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes

    ensure_bucket()

    user = User(email="plan@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()

    episode = Episode(user_id=user.id, title="Plan Test", description="d", tags="a,b", status="ready")
    for index, narration in enumerate(["Hello world", "Second line"]):
        episode.scenes.append(
            Scene(order_index=index, narration_text=narration, asset_object_key=None)
        )
    db_session.add(episode)
    db_session.commit()

    for scene in episode.scenes:
        key = f"episodes/{episode.id}/scenes/{scene.id}.png"
        upload_bytes(key, b"fake-png-bytes")
        scene.asset_object_key = key
    db_session.commit()

    job = Job(episode_id=episode.id, type="build", status="queued")
    db_session.add(job)
    db_session.commit()
    return episode, job.id


def _run(job_id, db_session_factory, tmp_path):
    fake_output_path = tmp_path / "fake_engine_output.mp4"
    fake_output_path.write_bytes(b"fake-mp4-bytes")
    with patch("saas.tts_providers.synthesize_scene", side_effect=_fake_synth), \
         patch("saas.tasks.get_audio_duration", return_value=2.5), \
         patch("saas.tasks.build_scene_clip"), \
         patch("saas.tasks.build_episode", return_value=str(fake_output_path)):
        run_build(job_id, db_session_factory)


@mock_aws
def test_build_uploads_production_plan(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, job_id = _make_episode(db_session, monkeypatch)

    _run(job_id, db_session_factory, tmp_path)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    assert job.status == "done"
    fresh.close()

    from saas.object_storage import get_s3_client

    body = get_s3_client().get_object(
        Bucket="whatif-test-bucket", Key=f"episodes/{episode.id}/production_plan.json"
    )["Body"].read()
    data = json.loads(body)
    assert data["version"] == "0.1"
    assert data["episode"]["title"] == "Plan Test"
    assert data["episode"]["tags"] == ["a", "b"]
    assert len(data["sections"]) == 1
    section = data["sections"][0]
    assert section["id"] == "main"
    assert [s["name"] for s in section["scenes"]] == ["scene_00", "scene_01"]
    assert [s["text"] for s in section["scenes"]] == ["Hello world", "Second line"]
    assert all(s["asset"].startswith(f"episodes/{episode.id}/scenes/") for s in section["scenes"])


@mock_aws
def test_plan_upload_failure_does_not_fail_build(db_session, db_session_factory, tmp_path, monkeypatch):
    episode, job_id = _make_episode(db_session, monkeypatch)

    with patch("saas.tasks.upload_bytes", side_effect=RuntimeError("s3 down")):
        _run(job_id, db_session_factory, tmp_path)

    fresh = db_session_factory()
    job = fresh.query(Job).filter_by(id=job_id).one()
    episode_row = fresh.query(Episode).filter_by(id=episode.id).one()
    assert job.status == "done"
    assert episode_row.status == "built"
    fresh.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/saas/test_build_plan.py -q`
Expected: FAIL — first test with `NoSuchKey` for `production_plan.json`; second test with `AttributeError: <module 'saas.tasks'> does not have the attribute 'upload_bytes'`.

- [ ] **Step 3: Wire the plan into `run_build`**

In `saas/tasks.py` add imports:

```python
import json
import logging
```

(with the other stdlib imports), and:

```python
from agent_video.production_plan import PlanScene, PlanSection, ProductionPlan

from .object_storage import upload_bytes
```

Add near the top of the module (after imports):

```python
logger = logging.getLogger(__name__)
```

In `run_build`, replace the engine-scene construction block (currently `engine_scenes = []` through `engine_episode = EngineEpisode(...)`) with:

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
            plan_key = f"episodes/{episode.id}/production_plan.json"
            try:
                upload_bytes(
                    plan_key,
                    json.dumps(plan.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"),
                )
            except Exception as exc:
                logger.warning("production plan upload failed (%s); continuing build", exc)
```

- [ ] **Step 4: Run the new tests and the whole suite**

Run: `python -m pytest tests/saas/test_build_plan.py -q`
Expected: 2 passed

Run: `python -m pytest tests/ -q`
Expected: all pass (pre-existing `tests/saas/test_tasks.py` builds have no series and one scene — plan construction and upload succeed inertly there).

- [ ] **Step 5: Commit**

```bash
git add saas/tasks.py tests/saas/test_build_plan.py
git commit -m "feat: SaaS build uploads production_plan.json artifact

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
