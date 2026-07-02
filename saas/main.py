"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

import os

from fastapi import FastAPI

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
    youtube,
)

app = FastAPI(title="What If API")


@app.on_event("startup")
async def validate_youtube_config() -> None:
    if os.environ.get("GOOGLE_CLIENT_ID"):
        from .youtube_auth import _fernet
        _fernet()  # raises RuntimeError if TOKEN_ENCRYPTION_KEY is missing or invalid
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
app.include_router(youtube.router)
