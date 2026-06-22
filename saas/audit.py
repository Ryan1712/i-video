"""The single entry point for writing audit_logs rows — append-only, called by every admin-mutating route."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog, User


def log_action(
    db: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: int,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.id,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=before,
        after_data=after,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry
