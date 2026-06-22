import os
from unittest.mock import patch

from agent_video.cli import slugify, next_episode_number, cmd_new, cmd_status, cmd_build


def test_slugify_lowercases_and_dashes():
    assert slugify("What If The Moon Disappeared") == "what-if-the-moon-disappeared"
    assert slugify("  Extra   Spaces!! ") == "extra-spaces"


def test_next_episode_number_starts_at_1(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(videos_dir)

    assert next_episode_number(videos_dir) == 1


def test_next_episode_number_increments_past_existing(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(os.path.join(videos_dir, "ep01_foo"))
    os.makedirs(os.path.join(videos_dir, "ep03_bar"))

    assert next_episode_number(videos_dir) == 4


def test_cmd_new_creates_expected_structure(tmp_path):
    videos_dir = str(tmp_path / "videos")
    os.makedirs(videos_dir)

    ep_dir = cmd_new("What If The Moon Disappeared", videos_dir)

    assert os.path.basename(ep_dir) == "ep01_what-if-the-moon-disappeared"
    assert os.path.isdir(os.path.join(ep_dir, "assets"))
    assert os.path.isdir(os.path.join(ep_dir, "audio"))
    assert os.path.isdir(os.path.join(ep_dir, "output"))
    assert os.path.isfile(os.path.join(ep_dir, "script.md"))
    content = open(os.path.join(ep_dir, "script.md"), encoding="utf-8").read()
    assert "title: What If The Moon Disappeared" in content
    assert "## scene_01" in content


def test_cmd_status_reports_missing_assets(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = cmd_status(ep_dir, assets_common_dir=common_dir)

    assert manifest["ready"] is False
    assert manifest["assets"][0]["asset"] == "hero.png"


def test_cmd_build_returns_none_when_assets_missing(tmp_path, capsys):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    result = cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    assert result is None
    captured = capsys.readouterr()
    assert "hero.png" in captured.out


def test_cmd_build_runs_full_pipeline_when_ready(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    open(os.path.join(ep_dir, "assets", "hero.png"), "wb").close()
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}):
        with patch("agent_video.cli.synthesize_scene") as synth_mock, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip") as clip_mock, \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")) as build_ep_mock:
            result = cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))

    assert result == os.path.join(ep_dir, "output", "episode.mp4")
    assert synth_mock.called
    assert clip_mock.called
    assert build_ep_mock.called
