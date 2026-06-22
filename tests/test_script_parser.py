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
