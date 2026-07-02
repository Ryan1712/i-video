"""Generic S3-compatible object storage wrapper (boto3); mockable with moto in tests."""
from __future__ import annotations

import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def _bucket_name() -> str:
    name = os.environ.get("S3_BUCKET_NAME")
    if not name:
        raise RuntimeError("S3_BUCKET_NAME environment variable is not set")
    return name


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    client = get_s3_client()
    bucket = _bucket_name()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("404", "NoSuchBucket"):
            raise
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        if region == "us-east-1":
            client.create_bucket(Bucket=bucket)
        else:
            client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )


def upload_bytes(key: str, content: bytes) -> None:
    client = get_s3_client()
    client.put_object(Bucket=_bucket_name(), Key=key, Body=content)


def download_to_path(key: str, local_path: str) -> None:
    client = get_s3_client()
    client.download_file(_bucket_name(), key, local_path)


def presigned_url(key: str, expires_in: int = 300) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket_name(), "Key": key},
        ExpiresIn=expires_in,
    )
