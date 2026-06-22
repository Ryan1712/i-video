"""Admin-only route guard, built on top of the existing get_current_user dependency."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from .deps import get_current_user
from .models import User


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
