# TTS Content-Hash Cache — Design

Date: 2026-07-16
Status: Approved

## Problem

Both build pipelines re-call the TTS provider for every scene on every build:

- CLI: `agent_video/cli.py` `cmd_build` loops all scenes and calls `synthesize_scene` unconditionally.
- SaaS: `saas/tasks.py` `build_episode_task` works in a tempdir that is deleted after the build (`shutil.rmtree`), so scene audio never survives to the next build.

A full EP1 build synthesizes ~9 minutes of narration across 37 scenes. Every review → edit one line → rebuild cycle pays the full ElevenLabs cost again. The current milestone (review EP1 → fix blocker → EP1 v1) is exactly the phase with the most rebuilds.

## Goals

- Rebuilding an episode only calls the TTS provider for scenes whose input actually changed.
- One shared implementation of the hash/caching logic used by both CLI and SaaS.
- A cache failure must never fail a build — worst case is a cache miss.

## Non-goals (deferred)

- Image / scene-clip / final-render caching (same pattern can be extended later).
- Cache eviction or size limits.
- Full per-job cost logging (separate roadmap item; this feature only logs hit/miss).

## Design

### Cache key

`compute_cache_key(fields: dict) -> str` — SHA-256 hex of the canonical JSON
(`sort_keys=True`, UTF-8) of `fields` plus an injected `"cache_version": TTS_CACHE_VERSION`.

`TTS_CACHE_VERSION` is a module constant (starts at 1). Bump it whenever TTS behavior
changes in a way that makes old audio stale (e.g. different post-processing), so the cache
can never return output produced by older pipeline logic.

Each call site declares exactly the fields that influence the audio output:

- ElevenLabs: `provider="elevenlabs"`, `model_id`, `voice`, `stability`, `similarity_boost`, `style`, `text`.
- Azure: `provider="azure"`, `voice`, `language`, `output_format`, `text`.
  (`style` is accepted-and-ignored by `AzureTTS`, so it is deliberately NOT part of the
  Azure key — including it would only cause pointless misses.)

### Flow

New engine module `agent_video/tts_cache.py`:

```python
def synthesize_with_cache(key_fields, synth_fn, out_path, store, force=False) -> bool:
    # returns True on cache hit
```

1. `key = compute_cache_key(key_fields)`
2. If not `force`: `store.fetch(key, out_path)` — on success return `True`.
3. Miss: call `synth_fn(out_path)`, then `store.store(key, out_path)`, return `False`.
4. Any exception raised by `fetch`/`store` is caught, logged as a warning, and treated as
   a miss / no-op. Synthesis errors propagate unchanged.

### Storage backends

Protocol: `fetch(key, dest_path) -> bool`, `store(key, src_path) -> None`.

- `LocalCacheStore(root_dir)` — in `agent_video/tts_cache.py`. Files at
  `<root>/<key>.mp3`. CLI uses `<videos_dir>/.tts_cache/`.
- `ObjectStorageCacheStore` — in `saas/` (keeps the engine free of SaaS imports).
  Objects at `tts_cache/<key>.mp3` in the existing bucket, via the existing
  `saas/object_storage.py` helpers. Cache is shared across all users by design:
  identical text + voice + settings produce identical audio, so cross-tenant reuse is
  safe and maximizes savings (decision confirmed 2026-07-15).

### Call-site changes

- CLI `cmd_build`: wrap the `synthesize_scene` call with `synthesize_with_cache` using
  `LocalCacheStore`. Print per-build summary (e.g. `Giọng đọc: 30/37 từ cache`).
- SaaS `build_episode_task`: wrap `tts.synthesize(...)` the same way with
  `ObjectStorageCacheStore`. Job stage string includes running hit count,
  e.g. `tts 12/37 (9 cached)`.

### Bypass

Env var `TTS_CACHE=off` disables the cache entirely in both pipelines: call sites
detect it and call `synth_fn` directly, bypassing `synthesize_with_cache` (no fetch,
no store). `force=True` is a separate knob: skip fetch but still store the fresh
result. Default is on.

## Testing

Unit (`tests/test_tts_cache.py`):
- Same fields → same key; each individual field change → different key; version bump → different key.
- Hit: `synth_fn` not called, `out_path` populated from store.
- Miss: `synth_fn` called once, result stored.
- Broken store (fetch/store raising): audio still produced, no exception escapes.
- `force=True` skips fetch.

Integration (`tests/saas/test_build_cache.py`):
- Run `build_episode_task` twice with a fake TTS provider that counts calls and a fake
  object storage; second build makes zero provider calls and produces identical audio set.
- Changing one scene's narration between builds → exactly one provider call on rebuild.
