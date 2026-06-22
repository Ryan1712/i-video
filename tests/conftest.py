import sys
from pathlib import Path

import pytest

# Add the repo root to sys.path so packages can be imported
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))


def pytest_configure(config):
    """Ensure repo root is in sys.path before any test collection."""
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


@pytest.fixture
def tmp_episode_dir(tmp_path):
    """A scratch episode folder: tmp_path/ep/ with assets/, audio/, output/ subfolders."""
    ep_dir = tmp_path / "ep"
    (ep_dir / "assets").mkdir(parents=True)
    (ep_dir / "audio").mkdir()
    (ep_dir / "output").mkdir()
    return ep_dir
