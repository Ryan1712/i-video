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
class ScriptSection:
    title: str
    mood: str | None = None
    intensity: float | None = None
    music: str | None = None
    scenes: list[Scene] = field(default_factory=list)


@dataclass
class Episode:
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    sections: list[ScriptSection] = field(default_factory=list)


_SCENE_HEADER_RE = re.compile(r"^##\s+(\S+)\s*$")
_FIELD_RE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")
_SECTION_HEADER_RE = re.compile(r"^##\s+SECTION:\s*(.+?)\s*$")
_SECTION_META_KEYS = ("mood", "intensity", "music")


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def parse_script(path: str) -> Episode:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = raw.splitlines()

    # Split into frontmatter (before first "## scene" header) and scene blocks.
    first_scene_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _SCENE_HEADER_RE.match(stripped) or _SECTION_HEADER_RE.match(stripped):
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

    # Parse section and scene blocks.
    sections: list[ScriptSection] = []
    scenes: list[Scene] = []
    current_section: ScriptSection | None = None
    current_name = None
    current_fields: dict[str, str] = {}

    def _flush_scene():
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
        scene = Scene(
            name=current_name,
            asset=current_fields["asset"].strip(),
            text=current_fields["text"].strip(),
        )
        scenes.append(scene)
        current_section.scenes.append(scene)

    def _set_section_meta(section: ScriptSection, key: str, value: str) -> None:
        if key == "intensity":
            try:
                parsed = float(value)
            except ValueError:
                raise ScriptParseError(
                    f"{path}: section '{section.title}' has invalid intensity '{value}'"
                ) from None
            if not 0.0 <= parsed <= 1.0:
                raise ScriptParseError(
                    f"{path}: section '{section.title}' intensity {parsed} outside [0, 1]"
                )
            section.intensity = parsed
        elif key == "mood":
            section.mood = value
        else:
            section.music = value

    for line in lines[first_scene_idx:]:
        stripped = line.strip()

        section_match = _SECTION_HEADER_RE.match(stripped)
        if section_match:
            _flush_scene()
            current_name = None
            current_fields = {}
            if current_section is not None and not current_section.scenes:
                raise ScriptParseError(
                    f"{path}: section '{current_section.title}' has no scenes"
                )
            current_section = ScriptSection(title=section_match.group(1))
            sections.append(current_section)
            continue

        header_match = _SCENE_HEADER_RE.match(stripped)
        if header_match:
            _flush_scene()
            if current_section is None:
                current_section = ScriptSection(title=title)
                sections.append(current_section)
            current_name = header_match.group(1)
            current_fields = {}
            continue

        if not stripped:
            continue
        m = _FIELD_RE.match(stripped)
        if m:
            key, value = m.group(1).lower(), m.group(2).strip()
            if current_name is not None:
                current_fields[key] = value
            elif current_section is not None and key in _SECTION_META_KEYS:
                _set_section_meta(current_section, key, value)
        elif current_name is not None and "text" in current_fields:
            # Allow multi-line narration text continuing on following lines.
            current_fields["text"] += " " + stripped

    _flush_scene()

    if current_section is not None and not current_section.scenes:
        raise ScriptParseError(f"{path}: section '{current_section.title}' has no scenes")
    if not scenes:
        raise ScriptParseError(f"{path}: no valid scenes parsed")

    return Episode(
        title=title, description=description, tags=tags, scenes=scenes, sections=sections
    )
