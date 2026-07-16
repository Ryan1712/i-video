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
