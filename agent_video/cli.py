"""CLI entry point: new, status, build, upload commands."""
from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv

from .config import load_config
from .image_builder import build_scene_clip
from .manifest import build_manifest, print_manifest_report, write_manifest
from .script_parser import ScriptParseError, parse_script
from .tts import get_audio_duration, synthesize_scene
from .video_builder import build_episode
from .youtube_uploader import upload_video

SCRIPT_TEMPLATE = """title: {title}
description:
tags:

## scene_01
asset: hero_intro.png
text: Viết câu thoại đầu tiên ở đây.
"""


def slugify(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def next_episode_number(videos_dir: str) -> int:
    existing = [d for d in os.listdir(videos_dir) if re.match(r"^ep(\d+)_", d)]
    numbers = [int(re.match(r"^ep(\d+)_", d).group(1)) for d in existing]
    return (max(numbers) + 1) if numbers else 1


def cmd_new(title: str, videos_dir: str) -> str:
    number = next_episode_number(videos_dir)
    slug = slugify(title)
    ep_dir = os.path.join(videos_dir, f"ep{number:02d}_{slug}")
    os.makedirs(os.path.join(ep_dir, "assets"))
    os.makedirs(os.path.join(ep_dir, "audio"))
    os.makedirs(os.path.join(ep_dir, "output"))
    with open(os.path.join(ep_dir, "script.md"), "w", encoding="utf-8") as f:
        f.write(SCRIPT_TEMPLATE.format(title=title))
    return ep_dir


def cmd_status(video_dir: str, assets_common_dir: str = "assets_common") -> dict:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    manifest = build_manifest(episode, video_dir, assets_common_dir)
    write_manifest(manifest, video_dir)
    print_manifest_report(manifest)
    return manifest


def cmd_build(video_dir: str, assets_common_dir: str = "assets_common", project_root: str = ".") -> str | None:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    manifest = build_manifest(episode, video_dir, assets_common_dir)
    write_manifest(manifest, video_dir)

    if not manifest["ready"]:
        print_manifest_report(manifest)
        return None

    print(f"Bước 1/4: Kiểm tra ảnh...                  ✓ Đủ {len(episode.scenes)}/{len(episode.scenes)} ảnh")

    config = load_config(video_dir, project_root=project_root)
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")

    audio_paths = []
    durations = []
    for scene in episode.scenes:
        audio_path = os.path.join(video_dir, "audio", f"{scene.name}.mp3")
        synthesize_scene(scene.text, audio_path, api_key, voice_id)
        duration = get_audio_duration(audio_path)
        audio_paths.append(audio_path)
        durations.append(duration)
    print(f"Bước 2/4: Tạo giọng đọc...                 ✓ {len(episode.scenes)} scene")

    clip_paths = []
    tmp_dir = os.path.join(video_dir, "output", "_tmp")
    asset_lookup = {item["asset"]: item["found_at"] for item in manifest["assets"]}
    for scene, duration in zip(episode.scenes, durations):
        clip_path = os.path.join(video_dir, "output", f"_clip_{scene.name}.mp4")
        build_scene_clip(asset_lookup[scene.asset], duration, clip_path, tmp_dir, config)
        clip_paths.append(clip_path)
    print("Bước 3/4: Dựng hình từng cảnh...           ✓ Xong")

    out_path = build_episode(episode, clip_paths, audio_paths, durations, video_dir, config)
    print("Bước 4/4: Ghép video + phụ đề + nhạc nền...✓ Xong")
    print(f"\nHoàn tất: {out_path}")
    return out_path


def cmd_upload(video_dir: str, privacy: str, client_secret_path: str, token_path: str) -> int:
    episode = parse_script(os.path.join(video_dir, "script.md"))
    video_path = os.path.join(video_dir, "output", "episode.mp4")
    if not os.path.isfile(video_path):
        print(f"Chưa có {video_path} — hãy chạy 'build' trước.")
        return 1

    print("Sắp upload:")
    print(f"  Tiêu đề: {episode.title}")
    print(f"  Chế độ:  {privacy}")
    print(f"  File:    {video_path}\n")
    answer = input("Xác nhận đăng video này lên YouTube? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Đã hủy, không upload.")
        return 1

    video_id = upload_video(video_path, episode, privacy, client_secret_path, token_path)
    print(f"Đã upload: https://youtu.be/{video_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="agent_video")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("title")
    new_parser.add_argument("--videos-dir", default="videos")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("video_dir")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("video_dir")

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("video_dir")
    upload_parser.add_argument("--public", action="store_true")
    upload_parser.add_argument("--unlisted", action="store_true")
    upload_parser.add_argument("--client-secret", default="client_secret.json")
    upload_parser.add_argument("--token-path", default=None)

    args = parser.parse_args(argv)

    try:
        if args.command == "new":
            ep_dir = cmd_new(args.title, args.videos_dir)
            print(f"Đã tạo: {ep_dir}")
            return 0

        if args.command == "status":
            cmd_status(args.video_dir)
            return 0

        if args.command == "build":
            result = cmd_build(args.video_dir)
            return 0 if result else 1

        if args.command == "upload":
            privacy = "public" if args.public else ("unlisted" if args.unlisted else "private")
            token_path = args.token_path or os.path.join(args.video_dir, ".yt_token.json")
            return cmd_upload(args.video_dir, privacy, args.client_secret, token_path)

        return 1
    except ScriptParseError as e:
        print(f"Lỗi: {e}")
        return 1
    except Exception as e:
        print(f"Lỗi không mong đợi: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
