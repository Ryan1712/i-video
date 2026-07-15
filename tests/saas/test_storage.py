# tests/saas/test_storage.py
from moto import mock_aws


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-key")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET_NAME", "whatif-test-bucket")


@mock_aws
def test_save_asset_uploads_and_returns_key(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_asset

    ensure_bucket()
    key = save_asset(episode_id=3, scene_id=7, filename="hero.png", content=b"fake-png-bytes")

    assert key == "episodes/3/scenes/7.png"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-png-bytes"


@mock_aws
def test_save_asset_preserves_extension(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket
    from saas.storage import save_asset

    ensure_bucket()
    key = save_asset(episode_id=1, scene_id=2, filename="photo.jpeg", content=b"x")

    assert key.endswith(".jpeg")


@mock_aws
def test_save_output_uploads_local_file_and_returns_key(tmp_path, monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_output

    ensure_bucket()
    local_path = tmp_path / "out.mp4"
    local_path.write_bytes(b"fake-mp4-bytes")

    key = save_output(episode_id=5, local_mp4_path=str(local_path))

    assert key == "episodes/5/output.mp4"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-mp4-bytes"


@mock_aws
def test_save_series_music_uploads_and_returns_key(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, get_s3_client
    from saas.storage import save_series_music

    ensure_bucket()
    key = save_series_music(series_id=2, filename="track.mp3", content=b"fake-mp3-bytes")

    assert key == "series/2/music.mp3"
    body = get_s3_client().get_object(Bucket="whatif-test-bucket", Key=key)["Body"].read()
    assert body == b"fake-mp3-bytes"


@mock_aws
def test_presigned_asset_url_and_presigned_output_url(monkeypatch):
    _set_s3_env(monkeypatch)
    from saas.object_storage import ensure_bucket, upload_bytes
    from saas.storage import presigned_asset_url, presigned_output_url

    ensure_bucket()
    upload_bytes("episodes/1/scenes/2.png", b"x")
    upload_bytes("episodes/1/output.mp4", b"y")

    asset_url = presigned_asset_url("episodes/1/scenes/2.png")
    output_url = presigned_output_url("episodes/1/output.mp4")

    assert "episodes/1/scenes/2.png" in asset_url
    assert "episodes/1/output.mp4" in output_url
