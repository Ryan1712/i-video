"""YouTube OAuth connect/disconnect and status endpoints."""
from __future__ import annotations

import os
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User, YouTubeConnection
from ..schemas import YouTubeConnectOut, YouTubeStatusOut
from ..youtube_auth import encrypt_token

router = APIRouter(prefix="/youtube", tags=["youtube"])

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _flow() -> Flow:
    cfg = {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uris": [os.environ["GOOGLE_OAUTH_REDIRECT_URI"]],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(
        cfg,
        scopes=SCOPES,
        redirect_uri=os.environ["GOOGLE_OAUTH_REDIRECT_URI"],
    )
    return flow


def _make_state(user_id: int) -> str:
    secret = os.environ["JWT_SECRET"]
    return jwt.encode(
        {"user_id": user_id, "exp": time.time() + 300},
        secret,
        algorithm="HS256",
    )


def _verify_state(state: str) -> int:
    secret = os.environ["JWT_SECRET"]
    try:
        payload = jwt.decode(state, secret, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="ERR_INVALID_OAUTH_STATE")


@router.get("/connect", response_model=YouTubeConnectOut)
def connect(current_user: User = Depends(get_current_user)):
    flow = _flow()
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=_make_state(current_user.id),
    )
    return YouTubeConnectOut(url=url)


@router.get("/callback")
def callback(code: str, state: str, db: Session = Depends(get_db)):
    user_id = _verify_state(state)
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    youtube = build("youtube", "v3", credentials=creds)
    ch = youtube.channels().list(part="snippet", mine=True).execute()
    channel = ch["items"][0]
    channel_id = channel["id"]
    channel_title = channel["snippet"]["title"]

    encrypted = encrypt_token(creds.refresh_token)

    existing = db.query(YouTubeConnection).filter_by(user_id=user_id).one_or_none()
    if existing:
        existing.channel_id = channel_id
        existing.channel_title = channel_title
        existing.encrypted_refresh_token = encrypted
    else:
        db.add(
            YouTubeConnection(
                user_id=user_id,
                channel_id=channel_id,
                channel_title=channel_title,
                encrypted_refresh_token=encrypted,
            )
        )
    db.commit()
    return {"channel_id": channel_id, "channel_title": channel_title}


@router.get("/status", response_model=YouTubeStatusOut)
def status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if not conn:
        return YouTubeStatusOut(connected=False)
    return YouTubeStatusOut(
        connected=True,
        channel_id=conn.channel_id,
        channel_title=conn.channel_title,
    )


@router.delete("/disconnect", status_code=204)
def disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = db.query(YouTubeConnection).filter_by(user_id=current_user.id).one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="ERR_YOUTUBE_NOT_CONNECTED")
    db.delete(conn)
    db.commit()
