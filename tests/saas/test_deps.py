import pytest
from fastapi import HTTPException

from saas.deps import get_current_user
from saas.models import User
from saas.security import create_access_token, hash_password

JWT_SECRET = "test-secret"


def test_get_current_user_returns_user_for_valid_token(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = User(email="x@example.com", password_hash=hash_password("pw"), role="user")
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, secret=JWT_SECRET)

    result = get_current_user(authorization=f"Bearer {token}", db=db_session)

    assert result.id == user.id
    assert result.email == "x@example.com"


def test_get_current_user_rejects_missing_header(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=None, db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer garbage", db=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_unknown_user_id(db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = create_access_token(user_id=99999, secret=JWT_SECRET)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", db=db_session)
    assert exc_info.value.status_code == 401
