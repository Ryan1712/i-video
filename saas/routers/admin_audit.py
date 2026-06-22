"""Audit log search/filter and CSV export, per spec: searchable by actor, action type, date range."""
from __future__ import annotations

import csv
import datetime
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..db import get_db
from ..models import AuditLog, User
from ..schemas import AuditLogOut

router = APIRouter(prefix="/admin/audit", tags=["admin"])


def _filtered_query(
    db: Session,
    actor_user_id: int | None,
    action: str | None,
    from_date: datetime.datetime | None,
    to_date: datetime.datetime | None,
):
    query = db.query(AuditLog)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if from_date is not None:
        query = query.filter(AuditLog.created_at >= from_date)
    if to_date is not None:
        query = query.filter(AuditLog.created_at <= to_date)
    return query.order_by(AuditLog.created_at.desc())


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    actor_user_id: int | None = None,
    action: str | None = None,
    from_date: datetime.datetime | None = None,
    to_date: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[AuditLog]:
    return _filtered_query(db, actor_user_id, action, from_date, to_date).all()


@router.get("/export.csv")
def export_audit_logs_csv(
    actor_user_id: int | None = None,
    action: str | None = None,
    from_date: datetime.datetime | None = None,
    to_date: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StreamingResponse:
    rows = _filtered_query(db, actor_user_id, action, from_date, to_date).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "actor_user_id", "actor_role", "action", "target_type", "target_id", "created_at"])
    for row in rows:
        writer.writerow([row.id, row.actor_user_id, row.actor_role, row.action, row.target_type, row.target_id, row.created_at])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
