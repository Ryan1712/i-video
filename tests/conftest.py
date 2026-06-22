import pytest


@pytest.fixture
def tmp_episode_dir(tmp_path):
    """A scratch episode folder: tmp_path/ep/ with assets/, audio/, output/ subfolders."""
    ep_dir = tmp_path / "ep"
    (ep_dir / "assets").mkdir(parents=True)
    (ep_dir / "audio").mkdir()
    (ep_dir / "output").mkdir()
    return ep_dir
