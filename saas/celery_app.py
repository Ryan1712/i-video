"""Celery app instance, Redis broker/backend."""
from __future__ import annotations

import os

from celery import Celery

celery_app = Celery(
    "saas",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)
