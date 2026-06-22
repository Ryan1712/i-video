"""Plan-limit enforcement, checked before creating a new episode."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from ..models import Episode, Plan, Subscription, User


class PlanLimitError(Exception):
    def __init__(self, code: str = "ERR_PLAN_LIMIT_REACHED"):
        super().__init__(code)
        self.code = code


def check_episode_limit(db: Session, user: User) -> None:
    subscription = db.query(Subscription).filter_by(user_id=user.id).one_or_none()
    if subscription is None:
        return

    plan = db.query(Plan).filter_by(id=subscription.plan_id).one_or_none()
    if plan is None:
        return

    limit = plan.limits.get("episodes_per_month")
    if limit is None:
        return

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    count = (
        db.query(Episode)
        .filter(Episode.user_id == user.id, Episode.created_at >= cutoff)
        .count()
    )
    if count >= limit:
        raise PlanLimitError()
