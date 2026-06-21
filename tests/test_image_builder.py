from unittest.mock import patch, MagicMock

from PIL import Image

from agent_video.config import DEFAULT_CONFIG
from agent_video.image_builder import build_scene_clip


def _make_test_image(path, width=400, height=300):
    Image.new("RGB", (width, height), color=(10, 20, 30)).save(path)


def test_build_scene_clip_invokes_ffmpeg_with_configured_dimensions(tmp_path):
    asset_path = str(tmp_path / "hero.png")
    _make_test_image(asset_path)
    out_path = str(tmp_path / "output" / "hero.mp4")
    tmp_dir = str(tmp_path / "tmp")

    config = {
        "video": {"width": 640, "height": 360, "fps": 24},
        "ken_burns": {"zoom_start": 1.0, "zoom_end": 1.2, "speed": 0.002},
    }

    fake_result = MagicMock(returncode=0, stderr="")
    with patch("agent_video.image_builder.subprocess.run", return_value=fake_result) as run_mock:
        build_scene_clip(asset_path, duration=2.0, out_path=out_path, tmp_dir=tmp_dir, config=config)

    assert run_mock.called
    cmd = run_mock.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "s=640x360" in cmd_str
    assert "fps=24" in cmd_str
    assert "zoom+0.002" in cmd_str
    assert "1.2" in cmd_str
    assert out_path in cmd


def test_build_scene_clip_raises_on_ffmpeg_failure(tmp_path):
    asset_path = str(tmp_path / "hero.png")
    _make_test_image(asset_path)
    out_path = str(tmp_path / "output" / "hero.mp4")
    tmp_dir = str(tmp_path / "tmp")

    fake_result = MagicMock(returncode=1, stderr="ffmpeg exploded")
    with patch("agent_video.image_builder.subprocess.run", return_value=fake_result):
        try:
            build_scene_clip(asset_path, duration=2.0, out_path=out_path, tmp_dir=tmp_dir, config=DEFAULT_CONFIG)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "ffmpeg exploded" in str(e)
