"""Build a single .srt subtitle file from per-scene text + durations."""
from __future__ import annotations

from .script_parser import Episode


def _format_ts(seconds: float) -> str:
    millis_total = round(seconds * 1000)
    hours, rem = divmod(millis_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(episode: Episode, durations: list[float], out_path: str) -> str:
    if len(durations) != len(episode.scenes):
        raise ValueError("durations length must match number of scenes")

    lines = []
    cursor = 0.0
    for i, (scene, duration) in enumerate(zip(episode.scenes, durations), start=1):
        start = cursor
        end = cursor + duration
        lines.append(str(i))
        lines.append(f"{_format_ts(start)} --> {_format_ts(end)}")
        lines.append(scene.text)
        lines.append("")
        cursor = end

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return out_path
