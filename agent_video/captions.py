"""Build a single .srt subtitle file from per-scene text + durations."""
from __future__ import annotations

import re

from .script_parser import Episode

# Roughly the longest chunk that still reads as 1-2 lines when burned in at the
# configured caption font size on a 1920px-wide frame — long uncut scene text
# was wrapping into 6+ lines and covering most of the image.
_MAX_CUE_CHARS = 90
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def _split_into_cues(text: str, max_chars: int = _MAX_CUE_CHARS) -> list[str]:
    text = text.strip()
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s]
    if not sentences:
        return [text] if text else []

    cues: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            cues.append(sentence)
            continue
        # A single sentence is still too long to read comfortably — break on
        # commas instead, since Vietnamese/English both use them as pause points.
        chunk = ""
        for part in sentence.split(","):
            piece = part.strip()
            candidate = f"{chunk}, {piece}" if chunk else piece
            if chunk and len(candidate) > max_chars:
                cues.append(chunk)
                chunk = piece
            else:
                chunk = candidate
        if chunk:
            cues.append(chunk)
    return cues


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
    cue_index = 1
    scene_start = 0.0
    for scene, duration in zip(episode.scenes, durations):
        cues = _split_into_cues(scene.text)
        total_chars = sum(len(c) for c in cues) or 1
        cursor = scene_start
        for i, cue_text in enumerate(cues):
            if i == len(cues) - 1:
                end = scene_start + duration  # pin to scene end, avoid float drift
            else:
                end = cursor + duration * (len(cue_text) / total_chars)
            lines.append(str(cue_index))
            lines.append(f"{_format_ts(cursor)} --> {_format_ts(end)}")
            lines.append(cue_text)
            lines.append("")
            cue_index += 1
            cursor = end
        scene_start += duration

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return out_path
