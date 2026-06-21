# What If Video Engine — Design Spec

## Context
The user runs a YouTube channel called "What If" (stick-figure / "người que" narrated videos, 16:9 long-form). They already write episode scripts/concepts with ChatGPT and will create character/scene images themselves (via ChatGPT Plus) to keep visual consistency — this engine does NOT auto-generate images. For each episode, the engine must read a user-authored script, determine which image assets are required and what filenames they must have, report missing assets back to the user, and once all required assets exist, automatically produce a narrated, captioned, motion video.

This spec covers the **core video-generation engine only** — the pipeline that turns a script + a folder of images into a finished mp4 and optionally uploads it to YouTube. It is designed to run as a CLI today, and to be re-hosted as a job executed by a Celery worker inside the larger SaaS platform (see the companion spec `2026-06-21-saas-platform-design.md`) without rewriting its core logic — only the entry point (CLI args vs. a job payload) and where it reads/writes files (local disk vs. object storage) change.

## Scope (v1)
- One episode processed per invocation — no batch/queue logic inside the engine itself (batching, if ever needed, is a job-scheduling concern of whatever calls the engine, not of the engine).
- Caption granularity: one caption per scene (the scene's full narration text), not word-level/karaoke timing.
- Background music: optional per-episode file, mixed at low volume under narration; absent if not provided.
- Upload to YouTube is a separate, explicitly invoked step with a confirmation gate — never triggered automatically by a successful build.

## Architecture
Five independent modules, each with a clear input/output contract, called in sequence:

```
script.md ──> [script_parser] ──> Episode(scenes[])
                                       │
                                       ▼
                              [manifest] ──> manifest.json (checks assets/ + assets_common/)
                                       │  (if not ready → print missing list, stop)
                                       ▼ (if ready)
                              [tts] ──> audio/scene_NN.mp3 (ElevenLabs, per scene)
                                       │
                                       ▼
                          [image_builder] ──> per-scene silent clip with Ken Burns pan/zoom
                                       │
                                       ▼
                            [captions] ──> one .srt for the whole episode
                                       │
                                       ▼
                          [video_builder] ──> ffmpeg: concat clips + mux audio +
                                               burn subtitles + mix optional music
                                       │
                                       ▼
                              output/episode.mp4
                                       │
                                       ▼ (separate, confirmed command)
                        [youtube_uploader] ──> YouTube (private by default)
```

## Components

### `script_parser.py`
Parses a user-written `script.md` (frontmatter: `title`, `description`, `tags`; scene blocks: `## scene_NN` with `asset:` and `text:` fields) into an `Episode(title, description, tags, scenes[])` dataclass. Raises a clear, scene-specific error on malformed input (missing `title`, missing `asset`/`text` in a scene) rather than guessing.

### `manifest.py`
For each scene, derives the required asset filename and checks it against the episode's `assets/` folder, then `assets_common/` (for assets reused across episodes, e.g. a recurring character pose). Writes `manifest.json` recording per-asset `status: ok|missing` and an overall `ready: bool`. When not ready, prints a human-readable report: each missing filename plus the scene's narration text, so the user knows what to create.

### `tts.py`
Calls the ElevenLabs API per scene to synthesize `audio/scene_NN.mp3`, then measures each clip's duration via ffprobe (or `ffmpeg -i` duration parsing as a fallback, since `imageio-ffmpeg` ships only the ffmpeg binary). Raises `TTSError` with an actionable message if `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` are missing.

### `image_builder.py`
Uses Pillow to "cover"-resize/crop each scene's asset to 1920x1080, then uses ffmpeg's `zoompan` filter to render a silent video clip with a slow Ken Burns zoom, length-matched to that scene's audio duration. Resolution/fps/zoom range are configurable (see Configuration below), not hardcoded.

### `captions.py`
Builds a single `.srt` for the episode: each scene's narration text becomes one subtitle cue, with start/end timestamps derived from the cumulative duration of preceding scenes' audio.

### `video_builder.py`
Orchestrates ffmpeg to: concatenate all per-scene silent clips, mux the concatenated audio track, burn the `.srt` onto the video (hardcoded subtitles, so they show regardless of whether the viewer has captions enabled), and — if the episode folder contains a `music.mp3` — mix it under the narration at a configurable low volume. Outputs `output/episode.mp4`.

### `youtube_uploader.py`
Separate, explicit command. First invocation triggers an OAuth desktop-app consent flow (browser opens once), caching a refresh token locally so subsequent uploads don't require re-login. Reads `title`/`description`/`tags` from the episode's script. Defaults to `privacyStatus=private`; a `--public`/`--unlisted` flag is required to change it. Always prints a final summary (title, privacy, file path) and requires an explicit `yes` confirmation before calling the YouTube Data API v3.

## Configuration
Values that previously risked being hardcoded (resolution, fps, Ken Burns zoom range/speed, background-music volume, caption font/size) live in a `config.yaml` at the project root, with optional per-episode `videos/<ep>/config.yaml` overrides. Secrets (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`) stay in `.env`, never in `config.yaml`.

> Note: when this engine is later embedded as a Celery task in the SaaS platform, these config values move into the `plans`/`site_settings` tables or per-job parameters described in the SaaS spec — `config.yaml` is the right shape for the standalone-CLI phase.

## CLI surface (current phase)
- `python -m agent_video new "<title>"` — scaffolds `videos/epNN_<slug>/` (auto-incrementing episode number, slugified title) with `assets/`, `audio/`, `output/` and a template `script.md`.
- `python -m agent_video status <video_dir>` — runs the manifest check only (no TTS calls), reports missing assets.
- `python -m agent_video build <video_dir>` — re-runs the manifest check; if not ready, prints the missing list and exits non-zero; if ready, runs the full pipeline (TTS → image build → captions → video assembly) and reports step-by-step progress.
- `python -m agent_video upload <video_dir> [--public|--unlisted]` — runs the upload flow described above.

All CLI output is in Vietnamese, step-numbered, and uses ✓/✗ markers; errors include an actionable hint (e.g. "Chưa có ELEVENLABS_API_KEY trong file .env — xem SETUP.md mục 1") rather than raw stack traces.

## Error handling
Any failure (ElevenLabs API error, ffmpeg non-zero exit, missing asset detected mid-run) stops the pipeline immediately with a clear message naming the failing scene/step. The engine never silently skips a step or produces a partial/guessed result.

## One-time setup (documented in `SETUP.md`, not automated)
- **ElevenLabs**: create an API key in the ElevenLabs dashboard, put it in `.env` as `ELEVENLABS_API_KEY`; pick or clone a voice for `ELEVENLABS_VOICE_ID`.
- **YouTube**: create a Google Cloud project → enable "YouTube Data API v3" → create an OAuth Client ID (type "Desktop app") → download `client_secret.json` into the project root. The first `upload` run opens a browser for one-time consent.

## Verification
1. Create `videos/ep00_test/script.md` with 2 scenes.
2. Run `build` with no assets present → confirm it prints exactly the 2 missing filenames + their scene text and exits non-zero.
3. Drop 2 placeholder 1920x1080 PNGs into `assets/` named per the script → re-run `build` → confirm `output/episode.mp4` is produced with both scenes' narrated audio, burned-in captions, and visible Ken Burns motion.
4. Inspect `manifest.json` and confirm `ready: true`.
5. Run `upload` without a `client_secret.json` present → confirm it fails with a clear, actionable message (no real upload during this verification step unless the user explicitly wants to test a real upload).
