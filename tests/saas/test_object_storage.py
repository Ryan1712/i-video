import os

import boto3
from moto import mock_aws


@mock_aws
def test_ensure_bucket_creates_bucket_if_missing(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket, get_s3_client

    ensure_bucket()

    client = get_s3_client()
    response = client.list_buckets()
    bucket_names = [b["Name"] for b in response["Buckets"]]
    assert "whatif-test-bucket" in bucket_names


@mock_aws
def test_ensure_bucket_is_idempotent(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket

    ensure_bucket()
    ensure_bucket()  # must not raise on the second call


@mock_aws
def test_upload_and_download_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import download_to_path, ensure_bucket, upload_bytes

    ensure_bucket()
    upload_bytes("episodes/1/scenes/2.png", b"fake-png-bytes")

    local_path = tmp_path / "downloaded.png"
    download_to_path("episodes/1/scenes/2.png", str(local_path))

    assert local_path.read_bytes() == b"fake-png-bytes"


@mock_aws
def test_presigned_url_contains_key_and_bucket(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")

    from saas.object_storage import ensure_bucket, presigned_url, upload_bytes

    ensure_bucket()
    upload_bytes("episodes/1/output.mp4", b"fake-mp4-bytes")

    url = presigned_url("episodes/1/output.mp4", expires_in=120)

    assert "whatif-test-bucket" in url
    assert "episodes/1/output.mp4" in url
