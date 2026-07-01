"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .object_storage import ensure_bucket
from .routers import (
    admin_audit,
    admin_plans,
    admin_settings,
    admin_transactions,
    admin_users,
    admin_vouchers,
    auth,
    billing,
    episodes,
    jobs,
)

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
app.include_router(admin_users.router)
app.include_router(admin_settings.router)
app.include_router(admin_audit.router)


@app.on_event("startup")
def _ensure_bucket_on_startup() -> None:
    ensure_bucket()
