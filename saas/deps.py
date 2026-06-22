"""FastAPI dependencies: current authenticated user."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import InvalidTokenError, decode_access_token, get_jwt_secret


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    secret = get_jwt_secret()

    try:
        user_id = decode_access_token(token, secret)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user
