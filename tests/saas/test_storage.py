import os

from saas.storage import get_asset_abs_path, save_asset


def test_save_asset_writes_file_and_returns_relative_path(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))

    relative_path = save_asset(episode_id=3, scene_id=7, filename="hero.png", content=b"fake-png-bytes")

    assert relative_path == os.path.join("episodes", "3", "scenes", "7.png")
    abs_path = get_asset_abs_path(relative_path)
    with open(abs_path, "rb") as f:
        assert f.read() == b"fake-png-bytes"


def test_save_asset_preserves_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))

    relative_path = save_asset(episode_id=1, scene_id=2, filename="photo.jpeg", content=b"x")

    assert relative_path.endswith(".jpeg")
