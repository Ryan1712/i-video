"""Build job: assembles a temp video_dir from DB rows, then reuses the existing engine unchanged."""
from __future__ import annotations

import os
import shutil
import tempfile

from sqlalchemy.orm import sessionmaker

from agent_video.config import DEFAULT_CONFIG
from agent_video.image_builder import build_scene_clip
from agent_video.script_parser import Episode as EngineEpisode
from agent_video.script_parser import Scene as EngineScene
from agent_video.tts import get_audio_duration, synthesize_scene
from agent_video.video_builder import build_episode

from .celery_app import celery_app
from .db import init_session_factory
from .models import Episode, Job
from .storage import get_asset_abs_path


def _episodes_dir() -> str:
    return os.environ.get("EPISODES_DIR", os.path.join("var", "episodes"))


def run_build(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
    job = None
    episode = None
    try:
        job = db.query(Job).filter_by(id=job_id).one()
        episode = db.query(Episode).filter_by(id=job.episode_id).one()

        job.status = "running"
        episode.status = "building"
        db.commit()

        temp_dir = tempfile.mkdtemp(prefix=f"ep{episode.id}_")
        try:
            os.makedirs(os.path.join(temp_dir, "audio"))
            os.makedirs(os.path.join(temp_dir, "output"))

            engine_scenes = []
            for scene in episode.scenes:
                scene_name = f"scene_{scene.order_index:02d}"
                engine_scenes.append(
                    EngineScene(name=scene_name, asset=get_asset_abs_path(scene.asset_path), text=scene.narration_text)
                )
            engine_episode = EngineEpisode(
                title=episode.title,
                description=episode.description,
                tags=[t.strip() for t in episode.tags.split(",") if t.strip()],
                scenes=engine_scenes,
            )

            config = DEFAULT_CONFIG
            audio_paths = []
            durations = []
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
            voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
            for scene in engine_episode.scenes:
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                synthesize_scene(scene.text, audio_path, api_key, voice_id)
                duration = get_audio_duration(audio_path)
                audio_paths.append(audio_path)
                durations.append(duration)

            clip_paths = []
            tmp_clip_dir = os.path.join(temp_dir, "output", "_tmp")
            for scene, duration in zip(engine_episode.scenes, durations):
                clip_path = os.path.join(temp_dir, "output", f"_clip_{scene.name}.mp4")
                build_scene_clip(scene.asset, duration, clip_path, tmp_clip_dir, config)
                clip_paths.append(clip_path)

            out_path = build_episode(engine_episode, clip_paths, audio_paths, durations, temp_dir, config)

            final_dir = os.path.join(_episodes_dir(), str(episode.id))
            os.makedirs(final_dir, exist_ok=True)
            final_path = os.path.join(final_dir, "episode.mp4")
            shutil.copyfile(out_path, final_path)

            episode.output_path = final_path
            episode.status = "built"
            job.status = "done"
            job.progress_pct = 100
            db.commit()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        if job is not None:
            job.status = "failed"
            job.error_message = str(e)
        if episode is not None:
            episode.status = "draft"
        db.commit()
    finally:
        db.close()


@celery_app.task(name="saas.tasks.build_episode_task")
def build_episode_task(job_id: int) -> None:
    run_build(job_id, init_session_factory())
