"""Derive required image assets from a parsed script and check them against disk."""
from __future__ import annotations

import json
import os

from .script_parser import Episode


def build_manifest(episode: Episode, video_dir: str, assets_common_dir: str) -> dict:
    assets_dir = os.path.join(video_dir, "assets")
    items = []
    all_ok = True

    for scene in episode.scenes:
        local_path = os.path.join(assets_dir, scene.asset)
        common_path = os.path.join(assets_common_dir, scene.asset)

        if os.path.isfile(local_path):
            status = "ok"
            found_at = local_path
        elif os.path.isfile(common_path):
            status = "ok"
            found_at = common_path
        else:
            status = "missing"
            found_at = None
            all_ok = False

        items.append(
            {
                "scene": scene.name,
                "asset": scene.asset,
                "scene_text": scene.text,
                "status": status,
                "found_at": found_at,
            }
        )

    manifest = {
        "title": episode.title,
        "ready": all_ok,
        "assets": items,
    }
    return manifest


def write_manifest(manifest: dict, video_dir: str) -> str:
    path = os.path.join(video_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return path


def print_manifest_report(manifest: dict) -> None:
    missing = [item for item in manifest["assets"] if item["status"] == "missing"]
    if not missing:
        print(f"[manifest] All {len(manifest['assets'])} assets present. Ready to build.")
        return

    print(f"[manifest] Missing {len(missing)} asset(s) for '{manifest['title']}':\n")
    for item in missing:
        print(f"  - {item['asset']}")
        print(f"      scene: {item['scene']}")
        print(f"      text:  {item['scene_text']}")
        print()
    print("Place these image files into the video's assets/ folder (or assets_common/ "
          "if reused across episodes), then re-run build.")
