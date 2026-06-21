"""Parse a user-authored script.md into an Episode of Scenes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class ScriptParseError(ValueError):
    pass


@dataclass
class Scene:
    name: str
    asset: str
    text: str


@dataclass
class Episode:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)


_SCENE_HEADER_RE = re.compile(r"^##\s+(\S+)\s*$")
_FIELD_RE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")


def parse_script(path: str) -> Episode:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = raw.splitlines()

    # Split into frontmatter (before first "## scene" header) and scene blocks.
    first_scene_idx = None
    for i, line in enumerate(lines):
        if _SCENE_HEADER_RE.match(line.strip()):
            first_scene_idx = i
            break

    if first_scene_idx is None:
        raise ScriptParseError(
            f"{path}: no scene blocks found (expected lines like '## scene_01')"
        )

    frontmatter_lines = lines[:first_scene_idx]
    fm = {}
    for line in frontmatter_lines:
        line = line.strip()
        if not line:
            continue
        m = _FIELD_RE.match(line)
        if m:
            fm[m.group(1).lower()] = m.group(2).strip()

    if "title" not in fm:
        raise ScriptParseError(f"{path}: missing required frontmatter field 'title'")

    title = fm["title"]
    description = fm.get("description", "")
    tags = [t.strip() for t in fm.get("tags", "").split(",") if t.strip()]

    # Parse scene blocks.
    scenes: list[Scene] = []
    current_name = None
    current_fields: dict[str, str] = {}

    def _flush():
        if current_name is None:
            return
        if "asset" not in current_fields:
            raise ScriptParseError(
                f"{path}: scene '{current_name}' is missing required field 'asset'"
            )
        if "text" not in current_fields or not current_fields["text"].strip():
            raise ScriptParseError(
                f"{path}: scene '{current_name}' is missing required field 'text'"
            )
        scenes.append(
            Scene(
                name=current_name,
                asset=current_fields["asset"].strip(),
                text=current_fields["text"].strip(),
            )
        )

    for line in lines[first_scene_idx:]:
        header_match = _SCENE_HEADER_RE.match(line.strip())
        if header_match:
            _flush()
            current_name = header_match.group(1)
            current_fields = {}
            continue

        stripped = line.strip()
        if not stripped:
            continue
        m = _FIELD_RE.match(stripped)
        if m:
            current_fields[m.group(1).lower()] = m.group(2).strip()
        elif "text" in current_fields:
            # Allow multi-line narration text continuing on following lines.
            current_fields["text"] += " " + stripped

    _flush()

    if not scenes:
        raise ScriptParseError(f"{path}: no valid scenes parsed")

    return Episode(title=title, description=description, tags=tags, scenes=scenes)
