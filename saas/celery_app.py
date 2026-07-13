"""Celery app instance, Redis broker/backend."""
from __future__ import annotations

import os

from celery import Celery
from celery.signals import worker_ready

celery_app = Celery(
    "saas",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    include=["saas.tasks"],
)


@worker_ready.connect
def _ensure_bucket_on_worker_ready(**kwargs) -> None:
    from .object_storage import ensure_bucket

    ensure_bucket()
