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
    parser.add_argument("--language", default=None)
    args = parser.parse_args()

    output_path = args.output or f"script_quality_ep{args.episode_id}.md"

    session_factory = init_session_factory()
    db = session_factory()
    try:
        episode = db.query(Episode).filter_by(id=args.episode_id).one()
        language = args.language
        if language is None:
            series_style = episode.series.style if episode.series else {}
            language = series_style.get("language", "en")
        plan = build_plan_from_db_episode(episode)
        plan.validate()
    finally:
        db.close()

    print(f"Checking {len(plan.flatten_scenes())} scenes...")
    flags = check_plan(plan)
    print(f"Rule checker: {len(flags)} flag(s) across {len({f.scene_name for f in flags})} scene(s)")

    print("Running LLM critique pass (one call for the whole episode)...")
    critiques = critique_script(plan, flags, language=language)
    print(f"LLM critic: {len(critiques)} scene(s) with issues")

    report = render_quality_report(plan, flags, critiques)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nWrote report: {output_path}")


if __name__ == "__main__":
    main()
