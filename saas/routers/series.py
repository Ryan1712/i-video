"""Series (project) CRUD and shared-asset routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Series, SeriesAsset, User
from ..schemas import AssetUrlOut, SeriesAssetOut, SeriesIn, SeriesOut
from ..storage import presigned_asset_url, save_series_asset

router = APIRouter(prefix="/series", tags=["series"])


def _get_owned_series_or_404(series_id: int, db: Session, current_user: User) -> Series:
    series = db.query(Series).filter_by(id=series_id, user_id=current_user.id).one_or_none()
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


def _to_out(series: Series, db: Session) -> SeriesOut:
    count = db.query(Episode).filter_by(series_id=series.id).count()
    out = SeriesOut.model_validate(series)
    out.episode_count = count
    return out


@router.post("", response_model=SeriesOut, status_code=201)
def create_series(
    payload: SeriesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesOut:
    series = Series(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        style=payload.style,
    )
    db.add(series)
    db.commit()
    return _to_out(series, db)


@router.get("", response_model=list[SeriesOut])
def list_series(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[SeriesOut]:
    all_series = db.query(Series).filter_by(user_id=current_user.id).all()
    return [_to_out(s, db) for s in all_series]


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesOut:
    return _to_out(_get_owned_series_or_404(series_id, db, current_user), db)


@router.get("/{series_id}/assets", response_model=list[SeriesAssetOut])
def list_series_assets(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SeriesAsset]:
    return _get_owned_series_or_404(series_id, db, current_user).assets


@router.post("/{series_id}/assets", response_model=SeriesAssetOut, status_code=201)
async def upload_series_asset(
    series_id: int,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SeriesAsset:
    series = _get_owned_series_or_404(series_id, db, current_user)
    asset = SeriesAsset(series_id=series.id, kind=kind, name=name, description=description)
    db.add(asset)
    db.flush()  # allocate asset.id for the object key

    content = await file.read()
    asset.object_key = save_series_asset(series.id, asset.id, file.filename, content)
    db.commit()
    return asset


@router.get("/{series_id}/assets/{asset_id}/url", response_model=AssetUrlOut)
def get_series_asset_url(
    series_id: int,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetUrlOut:
    series = _get_owned_series_or_404(series_id, db, current_user)
    asset = next((a for a in series.assets if a.id == asset_id), None)
    if asset is None or asset.object_key is None:
        raise HTTPException(status_code=404, detail="Series asset not found")
    return AssetUrlOut(url=presigned_asset_url(asset.object_key))
