# Object Storage Migration — Design Spec

## Context
The SaaS backend (auth, episodes/scenes/jobs, billing, admin) is built per `2026-06-21-saas-platform-design.md`, but scene assets and episode build output still live on local disk (`saas/storage.py`, `UPLOADS_DIR`/`EPISODES_DIR`), which doesn't survive a server replacement and doesn't scale across multiple Celery workers — a blocker called out in the platform spec. This spec covers swapping that local-disk layer for S3-compatible object storage (MinIO locally, any S3-compatible service in production), with no other behavior change. It is scoped independently from the related multi-tenant YouTube OAuth work (deferred to its own spec) since the two are unrelated subsystems.

## Components

```
saas/object_storage.py   — generic S3-compatible wrapper (boto3), mockable with moto in tests
  - ensure_bucket() -> None
  - upload_bytes(key: str, content: bytes) -> None
  - download_to_path(key: str, local_path: str) -> None
  - presigned_url(key: str, expires_in: int = 300) -> str

saas/storage.py          — domain-specific helpers (same role as today), thin wrapper over object_storage
  - save_asset(episode_id: int, scene_id: int, filename: str, content: bytes) -> str   (returns object key)
  - save_output(episode_id: int, local_mp4_path: str) -> str                            (returns object key)
  - presigned_asset_url(key: str) -> str
  - presigned_output_url(key: str) -> str
```

`storage.py` keeps the exact two-function-call shape `episodes.py` and `tasks.py` already depend on — only `object_storage.py` underneath changes from local disk to S3. `ensure_bucket()` is called once at API and worker startup (idempotent create-if-missing) so a fresh MinIO instance doesn't need manual bucket setup.

**New env vars** (added to `.env.example`): `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`.

**`docker-compose.yml`**: add a `minio` service (image `minio/minio`, port 9000 API + 9001 console) for local dev.

## Data model changes

- `Scene.asset_path` → renamed `asset_object_key` (same string column, now holds an S3 object key instead of a local relative path).
- `Episode.output_path` → renamed `output_object_key`.

No Alembic migration tool exists yet (tables are created via `Base.metadata.create_all`, per `SETUP.md` section 5.3) — this is a rename in the SQLAlchemy model; anyone with an existing local dev DB drops and recreates tables, consistent with how the project already handles schema changes pre-production.

## Data flow

### 1. Upload scene asset
`POST /episodes/{episode_id}/scenes/{scene_id}/asset` (route unchanged):
1. API reads bytes from the `UploadFile`.
2. `storage.save_asset(episode_id, scene_id, filename, content)` builds the key (`episodes/{episode_id}/scenes/{scene_id}{ext}`, same naming scheme as today) and calls `object_storage.upload_bytes(key, content)`.
3. `Scene.asset_object_key` is set to the returned key and committed.

No bytes touch local disk in this path.

### 2. Build job (`saas/tasks.py::run_build`)
1. `temp_dir` is created exactly as today.
2. For each scene, instead of resolving a local upload path, the task calls `object_storage.download_to_path(scene.asset_object_key, local_tmp_path)` to pull the asset into `temp_dir` before handing it to the engine. The engine (`agent_video/*`) is untouched — it still only ever sees local file paths.
3. After `build_episode()` produces the final mp4 at a local temp path, `storage.save_output(episode.id, out_path)` uploads it and returns the object key, stored on `Episode.output_object_key`.
4. `_episodes_dir()` and the `EPISODES_DIR` env var are removed — there is no longer a persistent local episodes directory; `temp_dir` is still cleaned up in the `finally` block as today.

### 3. Read-back (new)
Two small routes close the loop so a future frontend (or manual testing) can fetch files without the API proxying bytes:
- `GET /episodes/{episode_id}/scenes/{scene_id}/asset-url` → `{"url": "<presigned-url>"}`
- `GET /episodes/{episode_id}/output-url` → `{"url": "<presigned-url>"}`, 404 if `output_object_key` is not yet set

Both require `get_current_user` and the same ownership check `_get_owned_episode_or_404` already enforces on other episode routes. Presigned URLs expire after `expires_in` (default 300s) — short-lived by design since they're generated fresh on each request, never cached.

## Error handling
- `download_to_path` raising (key not found, network error) propagates as today's generic exception path in `run_build`'s `except Exception` block — job marked `failed`, episode reset to `draft`, error message stored. No new error-handling branch needed; this mirrors how a missing/corrupt local file already failed loudly before this change.
- `ensure_bucket()` failures at startup are fatal (let the process crash) — a missing/unreachable bucket means the API/worker can't function, the same posture as a missing `DATABASE_URL`.

## Testing
- Add `moto` to `requirements.txt` for mocking S3 at the network layer — no real network calls in the suite, consistent with how Stripe is already mocked.
- `tests/saas/test_object_storage.py` (new): `ensure_bucket`/`upload_bytes`/`download_to_path`/`presigned_url`, each under `@mock_aws`.
- `tests/saas/test_storage.py`: rewritten to assert against the mocked bucket instead of `UPLOADS_DIR`/`tmp_path`.
- `tests/saas/test_tasks.py`: patches `saas.tasks.download_to_path` / `saas.tasks.save_output` directly (keeping the existing mocks for `synthesize_scene`/`build_scene_clip`/`build_episode`); removes the local-file fixture setup.
- `tests/saas/test_episodes_routes.py`: add coverage for the two new presigned-url routes (happy path + 404/ownership cases).

## Documentation
`SETUP.md` section 5 (SaaS foundation) gains a step for starting MinIO, creating the bucket (or relying on `ensure_bucket()` auto-create), and setting the four new env vars.

## Out of scope (deferred)
- Multi-tenant YouTube OAuth and the upload job/route it requires — separate spec, unrelated subsystem.
- CDN/caching in front of presigned URLs.
- Configurable presigned-URL expiry per caller (fixed default is sufficient for v1).

## Verification
1. `pytest -q` passes with the rewritten storage/task/episode tests, no real network calls.
2. Local manual check: `docker compose up -d minio`, upload a scene asset via `POST /episodes/{id}/scenes/{scene_id}/asset`, confirm the object exists in the MinIO bucket (via console or `mc ls`), trigger a build, confirm `Episode.output_object_key` is set and `GET /episodes/{id}/output-url` returns a presigned URL that downloads the mp4.
