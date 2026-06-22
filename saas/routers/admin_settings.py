"""Admin-configurable site_settings, used for support-widget IDs/toggles."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import SiteSetting, User
from ..schemas import SiteSettingIn, SiteSettingOut

router = APIRouter(prefix="/admin/settings", tags=["admin"])


@router.get("", response_model=list[SiteSettingOut])
def list_settings(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[SiteSetting]:
    return db.query(SiteSetting).all()


@router.put("/{key}", response_model=SiteSettingOut)
def set_setting(
    key: str, payload: SiteSettingIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> SiteSetting:
    setting = db.query(SiteSetting).filter_by(key=key).one_or_none()
    before = {"value": setting.value} if setting is not None else None

    if setting is None:
        setting = SiteSetting(key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    db.commit()

    log_action(
        db, actor=current_user, action="setting.update", target_type="site_setting", target_id=0,
        before=before, after={"key": key, "value": payload.value},
    )
    return setting
