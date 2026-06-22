"""Password hashing and JWT access tokens."""
from __future__ import annotations

import datetime

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, secret: str, expires_minutes: int = 60 * 24) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + datetime.timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> int:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return int(payload["sub"])
    except jwt.PyJWTError as e:
        raise InvalidTokenError(str(e)) from e
