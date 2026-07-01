"""Tests for YouTube OAuth connect/callback/status/disconnect routes."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import User, YouTubeConnection
from saas.security import hash_password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FAKE_ENCRYPTION_KEY = Fernet.generate_key().decode()
_FAKE_JWT_SECRET = "test-yt-secret"
_FAKE_CLIENT_ID = "fake-client-id"
_FAKE_CLIENT_SECRET = "fake-client-secret"
_FAKE_REDIRECT_URI = "http://localhost/youtube/callback"


@pytest.fixture
def client(db_session_factory, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", _FAKE_JWT_SECRET)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _FAKE_ENCRYPTION_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _FAKE_CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", _FAKE_CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", _FAKE_REDIRECT_URI)

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_user_and_token(db_session_factory, monkeypatch=None) -> tuple[User, str]:
    """Create a user and return (user, access_token)."""
    import os
    from saas.security import create_access_token

    db = db_session_factory()
    user = User(email="ytuser@example.com", password_hash=hash_password("pw"), role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    secret = _FAKE_JWT_SECRET
    token = create_access_token(user.id, secret)
    db.close()
    return user, token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper: sign a state JWT for callback tests
# ---------------------------------------------------------------------------

def _make_state_jwt(user_id: int, secret: str = _FAKE_JWT_SECRET) -> str:
    import time
    return jwt.encode({"user_id": user_id, "exp": time.time() + 300}, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Test 1 – GET /youtube/connect returns a URL
# ---------------------------------------------------------------------------

def test_get_connect_url_returns_url(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)

    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = (
        "https://accounts.google.com/o/oauth2/auth?client_id=x",
        "state-value",
    )

    with patch("saas.routers.youtube.Flow.from_client_config", return_value=mock_flow):
        response = client.get("/youtube/connect", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert "url" in body
    assert body["url"].startswith("https://accounts.google.com/")


# ---------------------------------------------------------------------------
# Test 2 – GET /youtube/status when not connected
# ---------------------------------------------------------------------------

def test_get_status_not_connected(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)

    response = client.get("/youtube/status", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body.get("channel_id") is None
    assert body.get("channel_title") is None


# ---------------------------------------------------------------------------
# Test 3 – GET /youtube/status when connected
# ---------------------------------------------------------------------------

def test_get_status_connected(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)

    # Insert a YouTubeConnection row directly
    from saas.youtube_auth import encrypt_token

    db = db_session_factory()
    conn = YouTubeConnection(
        user_id=user.id,
        channel_id="UC_test_channel",
        channel_title="Test Channel",
        encrypted_refresh_token=encrypt_token("fake-refresh-token"),
    )
    db.add(conn)
    db.commit()
    db.close()

    response = client.get("/youtube/status", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["channel_id"] == "UC_test_channel"
    assert body["channel_title"] == "Test Channel"


# ---------------------------------------------------------------------------
# Test 4 – DELETE /youtube/disconnect removes connection
# ---------------------------------------------------------------------------

def test_disconnect_removes_connection(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)

    from saas.youtube_auth import encrypt_token

    db = db_session_factory()
    conn = YouTubeConnection(
        user_id=user.id,
        channel_id="UC_del",
        channel_title="Del Channel",
        encrypted_refresh_token=encrypt_token("rt"),
    )
    db.add(conn)
    db.commit()
    db.close()

    response = client.delete("/youtube/disconnect", headers=_auth_headers(token))

    assert response.status_code == 204

    # Verify row is gone
    db = db_session_factory()
    assert db.query(YouTubeConnection).filter_by(user_id=user.id).one_or_none() is None
    db.close()


# ---------------------------------------------------------------------------
# Test 5 – DELETE /youtube/disconnect 404 when not connected
# ---------------------------------------------------------------------------

def test_disconnect_no_connection_returns_404(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)

    response = client.delete("/youtube/disconnect", headers=_auth_headers(token))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 6 – GET /youtube/callback creates connection
# ---------------------------------------------------------------------------

def test_callback_creates_connection(client, db_session_factory):
    user, token = _create_user_and_token(db_session_factory)
    state = _make_state_jwt(user.id)

    # Mock the Flow
    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.refresh_token = "real-refresh-token"
    mock_flow.credentials = mock_creds

    # Mock the YouTube API service
    mock_channel_response = {
        "items": [
            {
                "id": "UC_new_channel",
                "snippet": {"title": "New Channel"},
            }
        ]
    }
    mock_youtube_service = MagicMock()
    (
        mock_youtube_service.channels.return_value
        .list.return_value
        .execute.return_value
    ) = mock_channel_response

    with (
        patch("saas.routers.youtube.Flow.from_client_config", return_value=mock_flow),
        patch("saas.routers.youtube.build", return_value=mock_youtube_service),
    ):
        response = client.get(f"/youtube/callback?code=auth-code&state={state}")

    assert response.status_code == 200
    body = response.json()
    assert body["channel_id"] == "UC_new_channel"
    assert body["channel_title"] == "New Channel"

    # Verify DB row created
    db = db_session_factory()
    conn = db.query(YouTubeConnection).filter_by(user_id=user.id).one_or_none()
    assert conn is not None
    assert conn.channel_id == "UC_new_channel"
    assert conn.encrypted_refresh_token != "real-refresh-token"  # should be encrypted
    db.close()


# ---------------------------------------------------------------------------
# Test 7 – GET /youtube/callback with invalid state returns 400
# ---------------------------------------------------------------------------

def test_callback_invalid_state_returns_400(client):
    tampered_state = "bad.state.jwt"

    response = client.get(f"/youtube/callback?code=some-code&state={tampered_state}")

    assert response.status_code == 400
