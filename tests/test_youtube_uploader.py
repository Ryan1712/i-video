from unittest.mock import patch, MagicMock

import pytest

from agent_video.script_parser import Episode, Scene
from agent_video.youtube_uploader import (
    build_upload_body,
    upload_video,
    MissingClientSecretError,
)


def _episode():
    return Episode(
        title="What If The Moon Disappeared",
        description="Khám phá...",
        tags=["whatif", "space"],
        scenes=[Scene(name="scene_01", asset="a.png", text="hi")],
    )


def test_build_upload_body_defaults_to_private():
    body = build_upload_body(_episode(), privacy="private")

    assert body["snippet"]["title"] == "What If The Moon Disappeared"
    assert body["snippet"]["description"] == "Khám phá..."
    assert body["snippet"]["tags"] == ["whatif", "space"]
    assert body["status"]["privacyStatus"] == "private"


def test_build_upload_body_accepts_public_or_unlisted():
    body = build_upload_body(_episode(), privacy="public")
    assert body["status"]["privacyStatus"] == "public"


def test_upload_video_raises_without_client_secret(tmp_path):
    missing_secret_path = str(tmp_path / "client_secret.json")

    with pytest.raises(MissingClientSecretError, match="client_secret.json"):
        upload_video(
            video_path=str(tmp_path / "episode.mp4"),
            episode=_episode(),
            privacy="private",
            client_secret_path=missing_secret_path,
            token_path=str(tmp_path / "token.json"),
        )


def test_upload_video_calls_youtube_api_with_built_body(tmp_path):
    client_secret_path = str(tmp_path / "client_secret.json")
    open(client_secret_path, "w").close()
    video_path = str(tmp_path / "episode.mp4")
    open(video_path, "wb").close()

    fake_request = MagicMock()
    fake_request.execute.return_value = {"id": "abc123"}
    fake_videos = MagicMock()
    fake_videos.insert.return_value = fake_request
    fake_service = MagicMock()
    fake_service.videos.return_value = fake_videos

    with patch("agent_video.youtube_uploader.get_authenticated_service", return_value=fake_service):
        with patch("agent_video.youtube_uploader.MediaFileUpload") as media_mock:
            video_id = upload_video(
                video_path=video_path,
                episode=_episode(),
                privacy="private",
                client_secret_path=client_secret_path,
                token_path=str(tmp_path / "token.json"),
            )

    assert video_id == "abc123"
    call_kwargs = fake_videos.insert.call_args[1]
    assert call_kwargs["body"]["status"]["privacyStatus"] == "private"
    media_mock.assert_called_once_with(video_path, chunksize=-1, resumable=True)
