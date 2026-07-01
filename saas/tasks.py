"""Build job: assembles a temp video_dir from DB rows, then reuses the existing engine unchanged."""
from __future__ import annotations

import os
import shutil
import tempfile

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build as build_youtube
from googleapiclient.http import MediaFileUpload
from sqlalchemy.orm import sessionmaker

from agent_video.config import DEFAULT_CONFIG
from agent_video.image_builder import build_scene_clip
from agent_video.script_parser import Episode as EngineEpisode
from agent_video.script_parser import Scene as EngineScene
from agent_video.tts import get_audio_duration, synthesize_scene
from agent_video.video_builder import build_episode

from .celery_app import celery_app
from .db import init_session_factory
from .models import Episode, Job, YouTubeConnection
from .storage import download_to_path, get_asset_abs_path
from .youtube_auth import decrypt_token


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


def run_upload(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
    job = None
    episode = None
    try:
        job = db.query(Job).filter_by(id=job_id).one()
        episode = db.query(Episode).filter_by(id=job.episode_id).one()

        job.status = "running"
        episode.status = "uploading"
        db.commit()

        conn = db.query(YouTubeConnection).filter_by(user_id=episode.user_id).one_or_none()
        if conn is None:
            raise RuntimeError("YouTube not connected")

        refresh_token = decrypt_token(conn.encrypted_refresh_token)
        creds = GoogleCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            local_path = f.name
        try:
            download_to_path(episode.output_object_key, local_path)
            youtube = build_youtube("youtube", "v3", credentials=creds)
            body = {
                "snippet": {
                    "title": episode.title,
                    "description": episode.description,
                    "tags": [t.strip() for t in episode.tags.split(",") if t.strip()],
                },
                "status": {"privacyStatus": "private"},
            }
            media = MediaFileUpload(local_path, chunksize=-1, resumable=True)
            response = youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            ).execute()
            episode.youtube_video_id = response["id"]
        finally:
            try:
                os.unlink(local_path)
            except OSError:
                pass  # Windows: file may still be held open by MediaFileUpload

        episode.status = "uploaded"
        job.status = "done"
        job.progress_pct = 100
        db.commit()

    except Exception as e:
        if job is not None:
            job.status = "failed"
            job.error_message = str(e)
        if episode is not None:
            episode.status = "built"  # revert so user can retry
        db.commit()
    finally:
        db.close()


@celery_app.task(name="saas.tasks.upload_episode_task")
def upload_episode_task(job_id: int) -> None:
    run_upload(job_id, init_session_factory())
