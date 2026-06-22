"""FastAPI app entry point, wires all routers together."""
from __future__ import annotations

from fastapi import FastAPI

from .routers import auth

app = FastAPI(title="What If API")
app.include_router(auth.router)
