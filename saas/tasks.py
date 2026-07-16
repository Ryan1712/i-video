"""Build job: assembles a temp video_dir from DB rows, then reuses the existing engine unchanged."""
from __future__ import annotations

import json
import logging
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
from agent_video.tts import get_audio_duration
from agent_video.tts_cache import synthesize_with_cache, tts_cache_enabled
from agent_video.video_builder import build_episode

from .celery_app import celery_app
from .db import init_session_factory
from .models import Episode, Job, YouTubeConnection
from .object_storage import upload_bytes
from .production_plan_builder import build_plan_from_db_episode
from .storage import download_to_path, save_output
from .tts_cache_store import ObjectStorageCacheStore
from .tts_providers import get_tts_provider
from .youtube_auth import decrypt_token

logger = logging.getLogger(__name__)


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
            os.makedirs(os.path.join(temp_dir, "assets"))
            os.makedirs(os.path.join(temp_dir, "output"))

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
            plan_key = f"episodes/{episode.id}/production_plan.json"
            try:
                upload_bytes(
                    plan_key,
                    json.dumps(plan.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"),
                )
            except Exception as exc:
                logger.warning("production plan upload failed (%s); continuing build", exc)

            config = DEFAULT_CONFIG
            audio_paths = []
            durations = []
            style = episode.series.style if episode.series else {}
            tts = get_tts_provider(style.get("tts_provider"))
            voice = style.get("voice_id", "")
            language = style.get("language", "en")
            voice_style = style.get("voice_style", 0.0)
            music_key = style.get("music_object_key")
            if music_key:
                download_to_path(music_key, os.path.join(temp_dir, "music.mp3"))
            total = len(engine_episode.scenes)
            cache_store = ObjectStorageCacheStore()
            cache_hits = 0
            for index, scene in enumerate(engine_episode.scenes):
                cache_note = f" ({cache_hits} cached)" if cache_hits else ""
                job.stage = f"tts {index + 1}/{total}{cache_note}"
                job.progress_pct = int((index + 1) / total * 50)
                db.commit()
                audio_path = os.path.join(temp_dir, "audio", f"{scene.name}.mp3")
                if tts_cache_enabled():
                    hit = synthesize_with_cache(
                        tts.cache_key_fields(scene.text, voice=voice, language=language, style=voice_style),
                        lambda p, t=scene.text: tts.synthesize(t, p, voice=voice, language=language, style=voice_style),
                        audio_path,
                        cache_store,
                    )
                    cache_hits += 1 if hit else 0
                else:
                    tts.synthesize(scene.text, audio_path, voice=voice, language=language, style=voice_style)
                duration = get_audio_duration(audio_path)
                audio_paths.append(audio_path)
                durations.append(duration)

            clip_paths = []
            tmp_clip_dir = os.path.join(temp_dir, "output", "_tmp")
            for index, (scene, duration) in enumerate(zip(engine_episode.scenes, durations)):
                job.stage = f"render {index + 1}/{total}"
                job.progress_pct = 50 + int((index + 1) / total * 40)
                db.commit()
                clip_path = os.path.join(temp_dir, "output", f"_clip_{scene.name}.mp4")
                build_scene_clip(scene.asset, duration, clip_path, tmp_clip_dir, config)
                clip_paths.append(clip_path)

            job.stage = "assemble"
            job.progress_pct = 95
            db.commit()
            out_path = build_episode(engine_episode, clip_paths, audio_paths, durations, temp_dir, config)

            output_key = save_output(episode.id, out_path)
            episode.output_object_key = output_key
            episode.status = "built"
            job.status = "done"
            job.stage = None
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

        if not episode.output_object_key:
            raise RuntimeError(
                "Episode has no S3 output key — the object-storage migration must be "
                "active and the episode must be built after that migration lands."
            )

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
