"""Job status route."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Episode, Job, User
from ..schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Job:
    job = (
        db.query(Job)
        .join(Episode, Episode.id == Job.episode_id)
        .filter(Job.id == job_id, Episode.user_id == current_user.id)
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
