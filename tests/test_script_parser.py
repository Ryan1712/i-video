import pytest

from agent_video.script_parser import parse_script, ScriptParseError


def _write_script(path, content):
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_parses_title_description_tags_and_scenes(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: What If The Moon Disappeared
description: Khám phá điều gì xảy ra
tags: whatif, space, science

## scene_01
asset: hero_intro.png
text: What if one day, the moon just vanished?

## scene_02
asset: hero_shocked.png
text: The tides would stop almost instantly.
""",
    )

    episode = parse_script(script_path)

    assert episode.title == "What If The Moon Disappeared"
    assert episode.description == "Khám phá điều gì xảy ra"
    assert episode.tags == ["whatif", "space", "science"]
    assert len(episode.scenes) == 2
    assert episode.scenes[0].name == "scene_01"
    assert episode.scenes[0].asset == "hero_intro.png"
    assert episode.scenes[0].text == "What if one day, the moon just vanished?"
    assert episode.scenes[1].name == "scene_02"


def test_multiline_text_is_joined_with_spaces(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: Test
description:
tags:

## scene_01
asset: hero.png
text: Line one
continues here.
""",
    )

    episode = parse_script(script_path)

    assert episode.scenes[0].text == "Line one continues here."


def test_missing_title_raises(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """## scene_01
asset: hero.png
text: hi
""",
    )

    with pytest.raises(ScriptParseError, match="missing required frontmatter field 'title'"):
        parse_script(script_path)


def test_scene_missing_asset_raises(tmp_episode_dir):
    script_path = _write_script(
        tmp_episode_dir / "script.md",
        """title: Test

## scene_01
text: hi
""",
    )

    with pytest.raises(ScriptParseError, match="scene 'scene_01' is missing required field 'asset'"):
        parse_script(script_path)


def test_no_scenes_raises(tmp_episode_dir):
    script_path = _write_script(tmp_episode_dir / "script.md", "title: Test\n")

    with pytest.raises(ScriptParseError, match="no scene blocks found"):
        parse_script(script_path)


def _write(tmp_path, content):
    path = str(tmp_path / "script.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


SECTIONED_SCRIPT = """title: Zombie EP1
description: d
tags: zombie

## SECTION: The First Signs
mood: suspense
intensity: 0.35
music: suspense-low

## scene_01
asset: street.png
text: At first, nobody knew.

## scene_02
asset: news.png
text: The news was confusing.

## SECTION: The Collapse
mood: panic

## scene_03
asset: hospital.png
text: Hospitals overflowed.
"""


def test_sectionless_script_gets_one_implicit_section(tmp_path):
    path = _write(tmp_path, "title: T\n\n## scene_01\nasset: a.png\ntext: hi\n")
    episode = parse_script(path)
    assert len(episode.sections) == 1
    section = episode.sections[0]
    assert section.title == "T"
    assert section.mood is None and section.intensity is None and section.music is None
    assert [s.name for s in section.scenes] == ["scene_01"]
    assert [s.name for s in episode.scenes] == ["scene_01"]


def test_sectioned_script_parses_sections_and_metadata(tmp_path):
    episode = parse_script(_write(tmp_path, SECTIONED_SCRIPT))
    assert [s.title for s in episode.sections] == ["The First Signs", "The Collapse"]
    first, second = episode.sections
    assert first.mood == "suspense"
    assert first.intensity == 0.35
    assert first.music == "suspense-low"
    assert [s.name for s in first.scenes] == ["scene_01", "scene_02"]
    assert second.mood == "panic"
    assert second.intensity is None and second.music is None
    assert [s.name for s in second.scenes] == ["scene_03"]
    # flat list unchanged for existing consumers
    assert [s.name for s in episode.scenes] == ["scene_01", "scene_02", "scene_03"]


def test_section_with_no_scenes_rejected(tmp_path):
    content = "title: T\n\n## SECTION: Empty\nmood: dark\n\n## SECTION: Real\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match="section 'Empty' has no scenes"):
        parse_script(_write(tmp_path, content))


def test_trailing_section_with_no_scenes_rejected(tmp_path):
    content = "title: T\n\n## scene_01\nasset: a.png\ntext: hi\n\n## SECTION: Tail\nmood: dark\n"
    with pytest.raises(ScriptParseError, match="section 'Tail' has no scenes"):
        parse_script(_write(tmp_path, content))


def test_invalid_intensity_rejected(tmp_path):
    content = "title: T\n\n## SECTION: A\nintensity: high\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match="invalid intensity 'high'"):
        parse_script(_write(tmp_path, content))


def test_out_of_range_intensity_rejected(tmp_path):
    content = "title: T\n\n## SECTION: A\nintensity: 1.5\n\n## scene_01\nasset: a.png\ntext: hi\n"
    with pytest.raises(ScriptParseError, match=r"intensity 1.5 outside \[0, 1\]"):
        parse_script(_write(tmp_path, content))


def test_section_metadata_does_not_leak_into_scene_fields(tmp_path):
    episode = parse_script(_write(tmp_path, SECTIONED_SCRIPT))
    assert episode.scenes[0].text == "At first, nobody knew."


def test_slugify_moved_to_script_parser():
    from agent_video.script_parser import slugify

    assert slugify("The First Signs!") == "the-first-signs"


def test_section_header_keyword_is_case_insensitive(tmp_path):
    content = "title: T\n\n## section: Opening\nmood: dark\n\n## scene_01\nasset: a.png\ntext: hi\n"
    episode = parse_script(_write(tmp_path, content))
    assert [s.title for s in episode.sections] == ["Opening"]
    assert episode.sections[0].mood == "dark"
    assert episode.scenes[0].text == "hi"
