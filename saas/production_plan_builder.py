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
