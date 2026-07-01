"""Episode and scene CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..billing.limits import PlanLimitError, check_episode_limit
from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Job, Scene, User
from ..schemas import AssetUrlOut, EpisodeIn, EpisodeOut, JobOut, OutputUrlOut, SceneOut
from ..storage import presigned_asset_url, presigned_output_url, save_asset
from ..tasks import build_episode_task

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.post("", response_model=EpisodeOut, status_code=201)
def create_episode(
    payload: EpisodeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    try:
        check_episode_limit(db, current_user)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=e.code)

    episode = Episode(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        status="draft",
    )
    for index, scene_in in enumerate(payload.scenes):
        episode.scenes.append(Scene(order_index=index, narration_text=scene_in.narration_text))

    db.add(episode)
    db.commit()
    return episode


@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Episode]:
    return db.query(Episode).filter_by(user_id=current_user.id).all()


def _get_owned_episode_or_404(episode_id: int, db: Session, current_user: User) -> Episode:
    episode = db.query(Episode).filter_by(id=episode_id, user_id=current_user.id).one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.get("/{episode_id}", response_model=EpisodeOut)
def get_episode(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    return _get_owned_episode_or_404(episode_id, db, current_user)


@router.post("/{episode_id}/scenes/{scene_id}/asset", response_model=SceneOut)
async def upload_scene_asset(
    episode_id: int,
    scene_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Scene:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    content = await file.read()
    key = save_asset(episode_id, scene_id, file.filename, content)
    scene.asset_object_key = key
    db.commit()
    return scene


@router.get("/{episode_id}/scenes/{scene_id}/asset-url", response_model=AssetUrlOut)
def get_scene_asset_url(
    episode_id: int,
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetUrlOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None or scene.asset_object_key is None:
        raise HTTPException(status_code=404, detail="Scene asset not found")
    return AssetUrlOut(url=presigned_asset_url(scene.asset_object_key))


@router.get("/{episode_id}/output-url", response_model=OutputUrlOut)
def get_output_url(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutputUrlOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if episode.output_object_key is None:
        raise HTTPException(status_code=404, detail="Episode output not built yet")
    return OutputUrlOut(url=presigned_output_url(episode.output_object_key))


@router.post("/{episode_id}/build", response_model=JobOut, status_code=202)
def trigger_build(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    try:
        check_episode_limit(db, current_user)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=e.code)

    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if any(scene.asset_object_key is None for scene in episode.scenes):
        raise HTTPException(status_code=400, detail="All scenes must have an uploaded asset before building")

    job = Job(episode_id=episode.id, type="build", status="queued")
    db.add(job)
    db.commit()

    build_episode_task.delay(job.id)
    return job
