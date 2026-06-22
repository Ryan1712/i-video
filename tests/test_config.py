import os

from agent_video.config import load_config, DEFAULT_CONFIG


def test_load_config_returns_defaults_when_no_files(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config == DEFAULT_CONFIG


def test_global_config_overrides_defaults(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        f.write("video:\n  width: 1280\n  height: 720\n")

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config["video"]["width"] == 1280
    assert config["video"]["height"] == 720
    assert config["video"]["fps"] == DEFAULT_CONFIG["video"]["fps"]  # untouched key preserved


def test_per_episode_config_overrides_global(tmp_path):
    video_dir = str(tmp_path / "ep")
    os.makedirs(video_dir)
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        f.write("ken_burns:\n  speed: 0.001\n")
    with open(os.path.join(video_dir, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("ken_burns:\n  speed: 0.005\n")

    config = load_config(video_dir, project_root=str(tmp_path))

    assert config["ken_burns"]["speed"] == 0.005
    assert config["ken_burns"]["zoom_end"] == DEFAULT_CONFIG["ken_burns"]["zoom_end"]
