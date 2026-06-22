import os
from unittest.mock import patch, MagicMock

from agent_video.config import DEFAULT_CONFIG
from agent_video.script_parser import Episode, Scene
from agent_video.video_builder import build_episode


def _episode():
    return Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[
            Scene(name="scene_01", asset="a.png", text="First line."),
            Scene(name="scene_02", asset="b.png", text="Second line."),
        ],
    )


def test_build_episode_runs_ffmpeg_without_music(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    clip_paths = [str(tmp_path / "scene_01.mp4"), str(tmp_path / "scene_02.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3"), str(tmp_path / "scene_02.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result) as run_mock, \
         patch("agent_video.video_builder.get_ffmpeg_exe", return_value="ffmpeg"):
        out_path = build_episode(
            _episode(), clip_paths, audio_paths, [2.5, 3.0], video_dir, DEFAULT_CONFIG
        )

    assert out_path == os.path.join(video_dir, "output", "episode.mp4")
    # last call is the final ffmpeg invocation
    final_cmd = " ".join(run_mock.call_args_list[-1][0][0])
    assert "subtitles=" in final_cmd
    assert "amix" not in final_cmd  # no music.mp3 present


def test_build_episode_mixes_music_when_present(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    open(os.path.join(video_dir, "music.mp3"), "wb").close()
    clip_paths = [str(tmp_path / "scene_01.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()

    episode = Episode(title="Test", description="", tags=[], scenes=[Scene(name="scene_01", asset="a.png", text="hi")])

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result) as run_mock, \
         patch("agent_video.video_builder.get_ffmpeg_exe", return_value="ffmpeg"):
        build_episode(episode, clip_paths, audio_paths, [2.0], video_dir, DEFAULT_CONFIG)

    final_cmd = " ".join(run_mock.call_args_list[-1][0][0])
    assert "amix" in final_cmd
    assert "0.18" in final_cmd  # DEFAULT_CONFIG music_volume


def test_build_episode_raises_on_ffmpeg_failure(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    os.makedirs(os.path.join(video_dir, "output"))
    clip_paths = [str(tmp_path / "scene_01.mp4")]
    audio_paths = [str(tmp_path / "scene_01.mp3")]
    for p in clip_paths + audio_paths:
        open(p, "wb").close()
    episode = Episode(title="Test", description="", tags=[], scenes=[Scene(name="scene_01", asset="a.png", text="hi")])

    fake_result = MagicMock(returncode=1, stderr="ffmpeg blew up")
    with patch("agent_video.video_builder.subprocess.run", return_value=fake_result), \
         patch("agent_video.video_builder.get_ffmpeg_exe", return_value="ffmpeg"):
        try:
            build_episode(episode, clip_paths, audio_paths, [2.0], video_dir, DEFAULT_CONFIG)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "ffmpeg blew up" in str(e)
