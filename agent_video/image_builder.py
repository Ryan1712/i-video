"""Turn a static scene asset into a silent video clip with a Ken Burns pan/zoom."""
from __future__ import annotations

import os
import subprocess

from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe


def _cover_resize(src_path: str, dst_path: str, width: int, height: int) -> None:
    """Resize+crop image to exactly width x height, preserving aspect ratio (cover)."""
    img = Image.open(src_path).convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = width / height

    if src_ratio > dst_ratio:
        new_height = height
        new_width = int(new_height * src_ratio)
    else:
        new_width = width
        new_height = int(new_width / src_ratio)

    img = img.resize((new_width, new_height), Image.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    img.save(dst_path)


def build_scene_clip(asset_path: str, duration: float, out_path: str, tmp_dir: str, config: dict) -> None:
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    width = config["video"]["width"]
    height = config["video"]["height"]
    fps = config["video"]["fps"]
    zoom_end = config["ken_burns"]["zoom_end"]
    speed = config["ken_burns"]["speed"]

    fitted_path = os.path.join(tmp_dir, f"_fitted_{os.path.basename(out_path)}.png")
    _cover_resize(asset_path, fitted_path, width, height)

    ffmpeg_exe = get_ffmpeg_exe()
    total_frames = max(int(duration * fps), 1)

    # Slow zoom-in (Ken Burns) over the duration of the clip.
    zoompan = (
        f"scale=8000:-1,"
        f"zoompan=z='min(zoom+{speed},{zoom_end})':d={total_frames}:s={width}x{height}:fps={fps}"
    )

    cmd = [
        ffmpeg_exe,
        "-y",
        "-loop",
        "1",
        "-i",
        fitted_path,
        "-vf",
        zoompan,
        "-t",
        str(duration),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed building clip for {asset_path}:\n{result.stderr[-2000:]}")

    os.remove(fitted_path)
