"""Load video/Ken Burns/audio/caption settings from config.yaml, with per-episode override."""
from __future__ import annotations

import os

import yaml

DEFAULT_CONFIG = {
    "video": {"width": 1920, "height": 1080, "fps": 30},
    "ken_burns": {"zoom_start": 1.0, "zoom_end": 1.15, "speed": 0.0008},
    "audio": {"music_volume": 0.18},
    "caption": {"font": "Arial", "font_size": 26},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(video_dir: str, project_root: str = ".") -> dict:
    config = DEFAULT_CONFIG

    global_path = os.path.join(project_root, "config.yaml")
    if os.path.isfile(global_path):
        config = _deep_merge(config, _load_yaml(global_path))

    local_path = os.path.join(video_dir, "config.yaml")
    if os.path.isfile(local_path):
        config = _deep_merge(config, _load_yaml(local_path))

    return config
