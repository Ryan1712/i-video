import os
from unittest.mock import patch

from agent_video.cli import slugify, next_episode_number, cmd_new, cmd_status, cmd_build, cmd_upload, main


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


def _make_episode_dir_with_script(tmp_path, with_video=False):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    if with_video:
        open(os.path.join(ep_dir, "output", "episode.mp4"), "wb").close()
    return ep_dir


def test_cmd_upload_missing_video_does_not_prompt_or_upload(tmp_path, capsys):
    ep_dir = _make_episode_dir_with_script(tmp_path, with_video=False)

    with patch("builtins.input") as input_mock, \
         patch("agent_video.cli.upload_video") as upload_mock:
        result = cmd_upload(ep_dir, "private", "client_secret.json", os.path.join(ep_dir, ".yt_token.json"))

    assert result == 1
    input_mock.assert_not_called()
    upload_mock.assert_not_called()
    captured = capsys.readouterr()
    assert "build" in captured.out.lower()


def test_cmd_upload_declined_confirmation_does_not_upload(tmp_path):
    ep_dir = _make_episode_dir_with_script(tmp_path, with_video=True)

    with patch("builtins.input", return_value="no"), \
         patch("agent_video.cli.upload_video") as upload_mock:
        result = cmd_upload(ep_dir, "private", "client_secret.json", os.path.join(ep_dir, ".yt_token.json"))

    assert result == 1
    upload_mock.assert_not_called()


def test_cmd_upload_confirmed_calls_upload_video(tmp_path):
    ep_dir = _make_episode_dir_with_script(tmp_path, with_video=True)
    client_secret_path = "client_secret.json"
    token_path = os.path.join(ep_dir, ".yt_token.json")
    video_path = os.path.join(ep_dir, "output", "episode.mp4")

    with patch("builtins.input", return_value="yes"), \
         patch("agent_video.cli.upload_video", return_value="abc123") as upload_mock:
        result = cmd_upload(ep_dir, "private", client_secret_path, token_path)

    assert result == 0
    upload_mock.assert_called_once()
    args = upload_mock.call_args[0]
    assert args[0] == video_path
    assert args[1].title == "Test"
    assert args[2] == "private"
    assert args[3] == client_secret_path
    assert args[4] == token_path


def test_main_status_handles_script_parse_error(tmp_path, capsys):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(ep_dir)
    # Malformed script.md (no scene blocks) -> parse_script raises ScriptParseError.
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\nno scenes here\n")

    result = main(["status", ep_dir])

    assert result == 1
    captured = capsys.readouterr()
    assert "Lỗi" in captured.out


def _fake_synth(text, out_path, api_key, voice_id, style=0.0):
    with open(out_path, "wb") as f:
        f.write(b"audio:" + text.encode("utf-8"))


def _build_ready_episode_dir(tmp_path):
    ep_dir = str(tmp_path / "ep")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hi\n")
    open(os.path.join(ep_dir, "assets", "hero.png"), "wb").close()
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)
    return ep_dir, common_dir


def test_cmd_build_second_run_uses_tts_cache(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)

    common_patches = dict(
        get_audio_duration=3.0,
        output=os.path.join(ep_dir, "output", "episode.mp4"),
    )
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}

    with patch.dict(os.environ, env):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth1, \
             patch("agent_video.cli.get_audio_duration", return_value=common_patches["get_audio_duration"]), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=common_patches["output"]):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth1.call_count == 1

        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth2, \
             patch("agent_video.cli.get_audio_duration", return_value=common_patches["get_audio_duration"]), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=common_patches["output"]):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth2.call_count == 0

    # cache lives next to the episode dir
    cache_dir = os.path.join(str(tmp_path), ".tts_cache")
    assert os.path.isdir(cache_dir)
    assert len(os.listdir(cache_dir)) == 1


def test_cmd_build_tts_cache_off_env_disables_cache(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v", "TTS_CACHE": "off"}

    with patch.dict(os.environ, env):
        for _ in range(2):
            with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth, \
                 patch("agent_video.cli.get_audio_duration", return_value=3.0), \
                 patch("agent_video.cli.build_scene_clip"), \
                 patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
                cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
            assert synth.call_count == 1

    assert not os.path.isdir(os.path.join(str(tmp_path), ".tts_cache"))


def test_cmd_build_changed_text_synthesizes_again(tmp_path):
    ep_dir, common_dir = _build_ready_episode_dir(tmp_path)
    env = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_VOICE_ID": "v"}

    with patch.dict(os.environ, env):
        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth1, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth1.call_count == 1

        with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
            f.write("title: Test\n\n## scene_01\nasset: hero.png\ntext: hello again\n")

        with patch("agent_video.cli.synthesize_scene", side_effect=_fake_synth) as synth2, \
             patch("agent_video.cli.get_audio_duration", return_value=3.0), \
             patch("agent_video.cli.build_scene_clip"), \
             patch("agent_video.cli.build_episode", return_value=os.path.join(ep_dir, "output", "episode.mp4")):
            cmd_build(ep_dir, assets_common_dir=common_dir, project_root=str(tmp_path))
        assert synth2.call_count == 1
