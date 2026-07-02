"""Tests for run_upload Celery task (moto S3 + mocked Google API)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

import boto3
import pytest
from cryptography.fernet import Fernet
from moto import mock_aws

from saas.models import Episode, Job, User, YouTubeConnection
from saas.tasks import run_upload
from saas.youtube_auth import encrypt_token

_FAKE_ENCRYPTION_KEY = Fernet.generate_key().decode()
_S3_BUCKET = "agent-video"
_OBJECT_KEY = "episodes/1/episode.mp4"


def _set_s3_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", _S3_BUCKET)
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # No S3_ENDPOINT_URL → moto intercepts standard AWS endpoints


def _setup_s3_bucket_and_file():
    """Create the moto S3 bucket and upload a fake mp4 object."""
    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    s3.create_bucket(Bucket=_S3_BUCKET)
    s3.put_object(Bucket=_S3_BUCKET, Key=_OBJECT_KEY, Body=b"fake-mp4-bytes")


def _make_user(db_session):
    user = User(email="uploader@example.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()
    return user


def _make_episode_and_job(db_session, user_id, status="built"):
    episode = Episode(
        user_id=user_id,
        title="Test Episode",
        description="A test description",
        tags="tag1,tag2",
        status=status,
        output_object_key=_OBJECT_KEY,
    )
    db_session.add(episode)
    db_session.commit()

    job = Job(episode_id=episode.id, type="upload", status="queued")
    db_session.add(job)
    db_session.commit()

    return episode, job


def _make_youtube_connection(db_session, user_id):
    conn = YouTubeConnection(
        user_id=user_id,
        channel_id="UC_test",
        channel_title="Test Channel",
        encrypted_refresh_token=encrypt_token("fake-refresh-token"),
    )
    db_session.add(conn)
    db_session.commit()
    return conn


def _make_fake_youtube_service(video_id="abc123"):
    """Return a mock YouTube API service whose videos().insert().execute() returns {"id": video_id}."""
    mock_service = MagicMock()
    mock_service.videos.return_value.insert.return_value.execute.return_value = {"id": video_id}
    return mock_service


@mock_aws
def test_run_upload_succeeds(db_session, db_session_factory, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _FAKE_ENCRYPTION_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-client-secret")
    _set_s3_env(monkeypatch)
    _setup_s3_bucket_and_file()

    user = _make_user(db_session)
    episode, job = _make_episode_and_job(db_session, user.id)
    _make_youtube_connection(db_session, user.id)

    fake_service = _make_fake_youtube_service("abc123")

    with patch("saas.tasks.GoogleCredentials") as mock_creds_cls, \
         patch("saas.tasks.build_youtube", return_value=fake_service):
        mock_creds_cls.return_value = MagicMock()
        run_upload(job.id, db_session_factory)

    fresh = db_session_factory()
    job_fresh = fresh.query(Job).filter_by(id=job.id).one()
    episode_fresh = fresh.query(Episode).filter_by(id=episode.id).one()
    assert job_fresh.status == "done"
    assert job_fresh.progress_pct == 100
    assert episode_fresh.status == "uploaded"
    assert episode_fresh.youtube_video_id == "abc123"
    fresh.close()


@mock_aws
def test_run_upload_marks_failed_on_api_error(db_session, db_session_factory, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _FAKE_ENCRYPTION_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-client-secret")
    _set_s3_env(monkeypatch)
    _setup_s3_bucket_and_file()

    user = _make_user(db_session)
    episode, job = _make_episode_and_job(db_session, user.id)
    _make_youtube_connection(db_session, user.id)

    mock_service = MagicMock()
    mock_service.videos.return_value.insert.return_value.execute.side_effect = HttpError(
        resp=MagicMock(status=500), content=b"quota exceeded"
    )

    with patch("saas.tasks.GoogleCredentials") as mock_creds_cls, \
         patch("saas.tasks.build_youtube", return_value=mock_service):
        mock_creds_cls.return_value = MagicMock()
        run_upload(job.id, db_session_factory)

    fresh = db_session_factory()
    job_fresh = fresh.query(Job).filter_by(id=job.id).one()
    episode_fresh = fresh.query(Episode).filter_by(id=episode.id).one()
    assert job_fresh.status == "failed"
    assert job_fresh.error_message is not None
    assert episode_fresh.status == "built"
    fresh.close()


@mock_aws
def test_run_upload_fails_if_not_connected(db_session, db_session_factory, monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", _FAKE_ENCRYPTION_KEY)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-client-secret")
    _set_s3_env(monkeypatch)
    _setup_s3_bucket_and_file()

    user = _make_user(db_session)
    episode, job = _make_episode_and_job(db_session, user.id)
    # No YouTubeConnection row added

    run_upload(job.id, db_session_factory)

    fresh = db_session_factory()
    job_fresh = fresh.query(Job).filter_by(id=job.id).one()
    episode_fresh = fresh.query(Episode).filter_by(id=episode.id).one()
    assert job_fresh.status == "failed"
    assert "not connected" in job_fresh.error_message.lower()
    assert episode_fresh.status == "built"
    fresh.close()
