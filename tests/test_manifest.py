import json
import os

from agent_video.manifest import build_manifest, write_manifest
from agent_video.script_parser import Episode, Scene


def _episode(scenes):
    return Episode(title="Test Episode", description="", tags=[], scenes=scenes)


def test_all_assets_missing(tmp_episode_dir, tmp_path):
    episode = _episode([
        Scene(name="scene_01", asset="hero.png", text="hi"),
    ])
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is False
    assert manifest["assets"][0]["status"] == "missing"
    assert manifest["assets"][0]["found_at"] is None
    assert manifest["assets"][0]["scene_text"] == "hi"


def test_asset_found_in_local_assets_dir(tmp_episode_dir, tmp_path):
    (tmp_episode_dir / "assets" / "hero.png").write_bytes(b"fake-png")
    episode = _episode([Scene(name="scene_01", asset="hero.png", text="hi")])
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is True
    assert manifest["assets"][0]["status"] == "ok"
    assert manifest["assets"][0]["found_at"].endswith("hero.png")


def test_asset_found_in_assets_common_fallback(tmp_episode_dir, tmp_path):
    common_dir = str(tmp_path / "assets_common")
    os.makedirs(common_dir)
    with open(os.path.join(common_dir, "recurring_hero.png"), "wb") as f:
        f.write(b"fake-png")
    episode = _episode([Scene(name="scene_01", asset="recurring_hero.png", text="hi")])

    manifest = build_manifest(episode, str(tmp_episode_dir), common_dir)

    assert manifest["ready"] is True
    assert manifest["assets"][0]["status"] == "ok"


def test_write_manifest_creates_json_file(tmp_episode_dir):
    manifest = {"title": "Test", "ready": True, "assets": []}

    path = write_manifest(manifest, str(tmp_episode_dir))

    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == manifest
