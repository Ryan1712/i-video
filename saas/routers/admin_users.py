"""Admin user management: list with current plan, suspend/unsuspend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import Plan, Subscription, User
from ..schemas import UserOut

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _to_user_out(db: Session, user: User) -> UserOut:
    subscription = db.query(Subscription).filter_by(user_id=user.id).one_or_none()
    plan_name = None
    if subscription is not None:
        plan = db.query(Plan).filter_by(id=subscription.plan_id).one_or_none()
        plan_name = plan.name if plan is not None else None
    return UserOut(id=user.id, email=user.email, role=user.role, is_suspended=user.is_suspended, plan_name=plan_name)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[UserOut]:
    users = db.query(User).all()
    return [_to_user_out(db, user) for user in users]


@router.post("/{user_id}/suspend", response_model=UserOut)
def suspend_user(
    user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> UserOut:
    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = True
    db.commit()
    log_action(db, actor=current_user, action="user.suspend", target_type="user", target_id=user.id)
    return _to_user_out(db, user)


@router.post("/{user_id}/unsuspend", response_model=UserOut)
def unsuspend_user(
    user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> UserOut:
    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = False
    db.commit()
    log_action(db, actor=current_user, action="user.unsuspend", target_type="user", target_id=user.id)
    return _to_user_out(db, user)
