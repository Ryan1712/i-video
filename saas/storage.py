"""Local-disk storage for user-uploaded scene assets (interim, pre-object-storage)."""
from __future__ import annotations

import os


def _uploads_root() -> str:
    return os.environ.get("UPLOADS_DIR", os.path.join("var", "uploads"))


def save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str:
    _, ext = os.path.splitext(filename)
    relative_path = os.path.join("episodes", str(episode_id), "scenes", f"{scene_id}{ext}")
    abs_path = os.path.join(_uploads_root(), relative_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(content)
    return relative_path


def get_asset_abs_path(relative_path: str) -> str:
    return os.path.join(_uploads_root(), relative_path)
