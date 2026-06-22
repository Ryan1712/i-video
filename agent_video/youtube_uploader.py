"""OAuth + YouTube Data API v3 upload, with a private-by-default confirmation gate."""
from __future__ import annotations

import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .script_parser import Episode

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class MissingClientSecretError(RuntimeError):
    pass


def build_upload_body(episode: Episode, privacy: str) -> dict:
    return {
        "snippet": {
            "title": episode.title,
            "description": episode.description,
            "tags": episode.tags,
        },
        "status": {"privacyStatus": privacy},
    }


def get_authenticated_service(client_secret_path: str, token_path: str):
    creds = None
    if os.path.isfile(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    episode: Episode,
    privacy: str,
    client_secret_path: str,
    token_path: str,
) -> str:
    if not os.path.isfile(client_secret_path):
        raise MissingClientSecretError(
            f"Không tìm thấy client_secret.json tại {client_secret_path}. "
            "Xem hướng dẫn ở SETUP.md mục YouTube."
        )

    service = get_authenticated_service(client_secret_path, token_path)
    body = build_upload_body(episode, privacy)
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    return response["id"]
