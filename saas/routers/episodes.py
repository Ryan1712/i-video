"""Episode and scene CRUD routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..ai.client import AIError
from ..ai.image_provider import ImageError, get_image_provider
from ..ai.script_analysis import analyze_script
from ..ai.script_generation import generate_script
from ..billing.limits import PlanLimitError, check_episode_limit
from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Job, Scene, Series, SeriesAsset, User, YouTubeConnection
from ..schemas import AnalyzeScriptIn, AssetUrlOut, EpisodeIn, EpisodeOut, GenerateScriptIn, JobOut, OutputUrlOut, SceneOut, ScriptOut
from ..storage import presigned_asset_url, presigned_output_url, save_asset, save_series_asset
from ..tasks import build_episode_task, upload_episode_task

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

    if payload.series_id is not None:
        series = db.query(Series).filter_by(id=payload.series_id, user_id=current_user.id).one_or_none()
        if series is None:
            raise HTTPException(status_code=404, detail="Series not found")

    episode = Episode(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        status="draft",
        series_id=payload.series_id,
        brief=payload.brief,
        target_duration_sec=payload.target_duration_sec,
    )
    for index, scene_in in enumerate(payload.scenes):
        episode.scenes.append(Scene(order_index=index, narration_text=scene_in.narration_text))

    db.add(episode)
    db.commit()
    return episode


@router.get("", response_model=list[EpisodeOut])
def list_episodes(
    series_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Episode]:
    query = db.query(Episode).filter_by(user_id=current_user.id)
    if series_id is not None:
        query = query.filter_by(series_id=series_id)
    return query.all()


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


@router.post("/{episode_id}/generate-script", response_model=ScriptOut)
def generate_episode_script(
    episode_id: int,
    payload: GenerateScriptIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScriptOut:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    style = episode.series.style if episode.series else {}
    try:
        script = generate_script(
            brief=payload.brief,
            target_duration_sec=payload.target_duration_sec,
            language=style.get("language", "en"),
            series_name=episode.series.name if episode.series else "",
            series_description=episode.series.description if episode.series else "",
        )
    except AIError:
        raise HTTPException(status_code=502, detail="ERR_SCRIPT_GENERATION_FAILED")

    episode.brief = payload.brief
    episode.target_duration_sec = payload.target_duration_sec
    episode.script = script
    db.commit()
    return ScriptOut(script=script)


@router.post("/{episode_id}/analyze-script", response_model=EpisodeOut)
def analyze_episode_script(
    episode_id: int,
    payload: AnalyzeScriptIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if episode.status != "draft":
        raise HTTPException(status_code=409, detail="ERR_EPISODE_NOT_DRAFT")

    series = episode.series
    style = series.style if series else {}
    assets = series.assets if series else []
    catalog = [
        {"id": a.id, "kind": a.kind, "name": a.name, "description": a.description}
        for a in assets
    ]
    try:
        analyzed = analyze_script(payload.script, style.get("language", "en"), catalog)
    except AIError:
        raise HTTPException(status_code=502, detail="ERR_SCRIPT_ANALYSIS_FAILED")

    assets_by_id = {a.id: a for a in assets}
    episode.script = payload.script
    episode.scenes.clear()
    for index, item in enumerate(analyzed):
        matched = assets_by_id.get(item["asset_id"]) if item["asset_id"] else None
        episode.scenes.append(
            Scene(
                order_index=index,
                narration_text=item["narration_text"],
                asset_object_key=matched.object_key if matched else None,
                asset_brief=item["asset_brief"],
            )
        )
    db.commit()
    db.refresh(episode)
    return episode


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


@router.post("/{episode_id}/scenes/{scene_id}/generate-asset", response_model=SceneOut)
def generate_scene_asset(
    episode_id: int,
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Scene:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    scene = next((s for s in episode.scenes if s.id == scene_id), None)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    if episode.series is None:
        raise HTTPException(status_code=400, detail="ERR_NO_SERIES")
    if not scene.asset_brief:
        raise HTTPException(status_code=400, detail="ERR_NO_ASSET_BRIEF")

    style_bible = episode.series.style.get("image_style_bible", "")
    prompt = scene.asset_brief if not style_bible else f"{scene.asset_brief}\n\nStyle: {style_bible}"
    try:
        content = get_image_provider().generate(prompt)
    except ImageError:
        raise HTTPException(status_code=502, detail="ERR_IMAGE_GENERATION_FAILED")

    asset = SeriesAsset(
        series_id=episode.series.id,
        kind="other",
        name=f"ep{episode.id}-scene{scene.order_index + 1}",
        description=scene.asset_brief,
        source="generated",
    )
    db.add(asset)
    db.flush()  # allocate asset.id for the object key
    asset.object_key = save_series_asset(episode.series.id, asset.id, "generated.png", content)
    scene.asset_object_key = asset.object_key
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


@router.get("/{episode_id}/jobs/latest", response_model=JobOut)
def get_latest_job(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    job = (
        db.query(Job)
        .filter_by(episode_id=episode.id)
        .order_by(Job.id.desc())
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="No jobs for this episode")
    return job


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


@router.post("/{episode_id}/upload", response_model=JobOut, status_code=202)
def trigger_upload(
    episode_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    episode = _get_owned_episode_or_404(episode_id, db, current_user)
    if episode.status != "built":
        raise HTTPException(status_code=409, detail="ERR_EPISODE_NOT_BUILT")
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if conn is None:
        raise HTTPException(status_code=409, detail="ERR_YOUTUBE_NOT_CONNECTED")

    job = Job(episode_id=episode.id, type="upload", status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    upload_episode_task.delay(job.id)
    return job
