"""Local-disk storage for user-uploaded scene assets (interim, pre-object-storage)."""
from __future__ import annotations

import os


def _uploads_root() -> str:
    return os.environ.get("UPLOADS_DIR", os.path.join("var", "uploads"))


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
    relative_path = os.path.join("episodes", str(episode_id), "scenes", f"{scene_id}{ext}")
    abs_path = os.path.join(_uploads_root(), relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(content)
    return relative_path


def get_asset_abs_path(relative_path: str) -> str:
    return os.path.join(_uploads_root(), relative_path)


def download_to_path(object_key: str, local_path: str) -> None:
    """Download an S3 object to a local file path."""
    _s3_client().download_file(_bucket(), object_key, local_path)


def upload_bytes(object_key: str, content: bytes) -> None:
    """Upload bytes to S3 under the given key."""
    import io

    _s3_client().upload_fileobj(io.BytesIO(content), _bucket(), object_key)
