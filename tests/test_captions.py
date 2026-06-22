import pytest

from agent_video.captions import build_srt
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


def test_mismatched_durations_length_raises():
    episode = Episode(
        title="Test",
        description="",
        tags=[],
        scenes=[Scene(name="scene_01", asset="a.png", text="hi")],
    )

    with pytest.raises(ValueError, match="durations length must match"):
        build_srt(episode, [1.0, 2.0], "/tmp/unused.srt")
