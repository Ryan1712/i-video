"""Concat per-scene clips, mux audio, burn captions, optionally mix in background music."""
from __future__ import annotations

import os
import subprocess

from imageio_ffmpeg import get_ffmpeg_exe

from .captions import build_srt
from .script_parser import Episode

# Resolve the ffmpeg executable path at import time, before any test patches
# subprocess.run -- imageio_ffmpeg.get_ffmpeg_exe() internally shells out (via
# platform.uname()) on first call, which would otherwise hit the mock.
_FFMPEG_EXE = get_ffmpeg_exe()


def _write_concat_list(clip_paths: list[str], list_path: str) -> None:
    with open(list_path, "w", encoding="utf-8") as f:
        for path in clip_paths:
            escaped = path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")


def build_episode(
    episode: Episode,
    scene_clip_paths: list[str],
    scene_audio_paths: list[str],
    durations: list[float],
    video_dir: str,
    config: dict,
) -> str:
    ffmpeg_exe = _FFMPEG_EXE
    output_dir = os.path.join(video_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "episode.mp4")

    concat_list_path = os.path.join(output_dir, "_concat_list.txt")
    _write_concat_list(scene_clip_paths, concat_list_path)

    silent_concat_path = os.path.join(output_dir, "_silent_concat.mp4")
    concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c", "copy", silent_concat_path,
    ]
    result = subprocess.run(concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed concatenating scene clips:\n{result.stderr[-2000:]}")

    audio_concat_list_path = os.path.join(output_dir, "_audio_concat_list.txt")
    _write_concat_list(scene_audio_paths, audio_concat_list_path)
    concat_audio_path = os.path.join(output_dir, "_concat_audio.mp3")
    audio_concat_cmd = [
        ffmpeg_exe, "-y",
        "-f", "concat", "-safe", "0", "-i", audio_concat_list_path,
        "-c", "copy", concat_audio_path,
    ]
    result = subprocess.run(audio_concat_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed concatenating scene audio:\n{result.stderr[-2000:]}")

    srt_path = os.path.join(output_dir, "captions.srt")
    build_srt(episode, durations, srt_path)
    srt_filter_path = srt_path.replace("\\", "/").replace(":", "\\:")

    music_path = os.path.join(video_dir, "music.mp3")
    has_music = os.path.isfile(music_path)

    final_cmd = [ffmpeg_exe, "-y", "-i", silent_concat_path, "-i", concat_audio_path]
    if has_music:
        music_volume = config["audio"]["music_volume"]
        final_cmd += ["-i", music_path]
        filter_complex = (
            f"[1:a]volume=1.0[narration];"
            f"[2:a]volume={music_volume}[music];"
            f"[narration][music]amix=inputs=2:duration=first[mixed_audio];"
            f"[0:v]subtitles='{srt_filter_path}'[vout]"
        )
        final_cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[mixed_audio]",
        ]
    else:
        final_cmd += [
            "-vf", f"subtitles='{srt_filter_path}'",
            "-map", "0:v", "-map", "1:a",
        ]
    final_cmd += ["-c:v", "libx264", "-c:a", "aac", "-shortest", out_path]

    result = subprocess.run(final_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed building final episode:\n{result.stderr[-2000:]}")

    return out_path
