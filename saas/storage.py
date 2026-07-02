"""Domain-specific S3 key naming for scene assets and episode output, thin wrapper over object_storage.py."""
from __future__ import annotations

import os

from .object_storage import presigned_url, upload_bytes


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "test"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "test"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )


def _bucket() -> str:
    return os.environ.get("S3_BUCKET_NAME", "agent-video")


def save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    key = f"episodes/{episode_id}/scenes/{scene_id}{ext}"
    upload_bytes(key, content)
    return key


def save_output(episode_id: int, local_mp4_path: str) -> str:
    key = f"episodes/{episode_id}/output.mp4"
    with open(local_mp4_path, "rb") as f:
        upload_bytes(key, f.read())
    return key


def download_to_path(object_key: str, local_path: str) -> None:
    _s3_client().download_file(_bucket(), object_key, local_path)


def presigned_asset_url(key: str) -> str:
    return presigned_url(key)


def presigned_output_url(key: str) -> str:
    return presigned_url(key)
