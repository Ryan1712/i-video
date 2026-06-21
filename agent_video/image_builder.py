"""Turn a static scene asset into a silent video clip with a Ken Burns pan/zoom."""
from __future__ import annotations

import os
import subprocess

from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe

WIDTH, HEIGHT = 1920, 1080
FPS = 30


def _cover_resize(src_path: str, dst_path: str) -> None:
    """Resize+crop image to exactly WIDTHxHEIGHT, preserving aspect ratio (cover)."""
    img = Image.open(src_path).convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = WIDTH / HEIGHT

    if src_ratio > dst_ratio:
        new_height = HEIGHT
        new_width = int(new_height * src_ratio)
    else:
        new_width = WIDTH
        new_height = int(new_width / src_ratio)

    img = img.resize((new_width, new_height), Image.LANCZOS)
    left = (new_width - WIDTH) // 2
    top = (new_height - HEIGHT) // 2
    img = img.crop((left, top, left + WIDTH, top + HEIGHT))
    img.save(dst_path)


def build_scene_clip(asset_path: str, duration: float, out_path: str, tmp_dir: str) -> None:
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fitted_path = os.path.join(tmp_dir, f"_fitted_{os.path.basename(out_path)}.png")
    _cover_resize(asset_path, fitted_path)

    ffmpeg_exe = get_ffmpeg_exe()
    total_frames = max(int(duration * FPS), 1)

    # Slow zoom-in (Ken Burns) over the duration of the clip.
    zoompan = (
        f"scale=8000:-1,"
        f"zoompan=z='min(zoom+0.0008,1.15)':d={total_frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
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
        str(FPS),
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed building clip for {asset_path}:\n{result.stderr[-2000:]}")

    os.remove(fitted_path)
