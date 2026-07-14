import pytest

from agent_video.captions import _split_into_cues, build_srt
from agent_video.script_parser import Episode, Scene


def test_build_srt_writes_sequential_cues(tmp_path):
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[
            Scene(name="scene_01", asset="a.png", text="First line."),
            Scene(name="scene_02", asset="b.png", text="Second line."),
        ],
    )
    out_path = str(tmp_path / "out.srt")

    build_srt(episode, [2.5, 3.0], out_path)

    content = open(out_path, encoding="utf-8").read()
    assert "1\n00:00:00,000 --> 00:00:02,500\nFirst line." in content
    assert "2\n00:00:02,500 --> 00:00:05,500\nSecond line." in content


def test_long_scene_text_splits_into_multiple_timed_cues(tmp_path):
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[
            Scene(
                name="scene_01",
                asset="a.png",
                text="Short first sentence. This is a much longer second sentence that goes on.",
            ),
        ],
    )
    out_path = str(tmp_path / "out.srt")

    build_srt(episode, [10.0], out_path)

    content = open(out_path, encoding="utf-8").read()
    blocks = [b for b in content.strip().split("\n\n") if b]
    assert len(blocks) == 2
    # Cue 1 starts at the scene start and hands off exactly where cue 2 begins.
    assert blocks[0].startswith("1\n00:00:00,000 -->")
    assert "Short first sentence." in blocks[0]
    assert "This is a much longer second sentence" in blocks[1]
    # Last cue ends exactly at the scene duration (no drift from proportional splits).
    assert blocks[1].splitlines()[1].endswith("--> 00:00:10,000")


def test_split_into_cues_caps_every_cue_even_without_commas():
    # A single comma-delimited segment longer than max_chars must still be
    # wrapped, not emitted whole (that let 80+ char lines through uncapped).
    text = (
        "But when hundreds of thousands of people think the same thing on the "
        "same morning, the result is a nightmare traffic jam"
    )
    cues = _split_into_cues(text, max_chars=55)
    assert cues  # non-empty
    for cue in cues:
        assert len(cue) <= 55, cue
    assert " ".join(cues) == text


def test_mismatched_durations_length_raises():
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[Scene(name="scene_01", asset="a.png", text="hi")],
    )

    with pytest.raises(ValueError, match="durations length must match"):
        build_srt(episode, [1.0, 2.0], "/tmp/unused.srt")
