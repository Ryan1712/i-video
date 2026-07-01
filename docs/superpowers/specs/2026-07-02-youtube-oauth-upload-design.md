# YouTube OAuth Connect & Upload Job — Design Spec

## Context

The backend already has `agent_video/youtube_uploader.py` for CLI-based uploads
(uses `InstalledAppFlow` + local token file). For the SaaS, uploads must be
triggered via API by an authenticated user who has pre-connected their YouTube
channel through a web OAuth flow. The CLI uploader is NOT reused — we build
credentials directly from the stored refresh token.

The `jobs` table already has `type (build|upload)`, and `youtube_connections`
is already defined in the platform data model. This spec fills in the
implementation of that table plus the connect/upload flows.

---

## Data model

### `youtube_connections` (new table)

```
id                  int PK
user_id             int FK → users.id, unique (one connection per user)
channel_id          str   — YouTube channel ID (UCxxxx), stored for display
channel_title       str   — human-readable channel name, stored for display
encrypted_refresh_token  str  — Fernet-encrypted refresh token
created_at          datetime
updated_at          datetime
```

`user_id` has a UNIQUE constraint — one YouTube connection per user. Re-connecting
replaces the existing row (upsert).

### Encryption

Refresh tokens are encrypted at rest with **Fernet** symmetric encryption
(`cryptography` library, already available transitively via `google-auth`).

Key source: `TOKEN_ENCRYPTION_KEY` env var — a URL-safe base64-encoded 32-byte
key (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).

A missing or invalid key raises `RuntimeError` at startup (not silently ignored).

---

## OAuth flow

Google OAuth 2.0 for Web Applications (not InstalledAppFlow).

**Required Google Cloud setup:**
- OAuth 2.0 Client ID of type "Web application"
- Authorized redirect URI: `{API_BASE_URL}/youtube/callback`

**Env vars:**
```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/youtube/callback
```

### Endpoints

#### `GET /youtube/connect`
- Requires: authenticated user
- Generates OAuth authorization URL with `state=<signed JWT containing user_id>`
- Returns: `{"url": "<google-auth-url>"}` — frontend redirects the user there

The `state` parameter is a short-lived JWT (5-minute expiry) signed with
`JWT_SECRET`, carrying `{"user_id": <int>}`. This avoids a server-side
session store and is safe because the callback verifies the signature.

#### `GET /youtube/callback?code=<>&state=<>`
- No auth header (Google redirects here with no Authorization header)
- Verifies `state` JWT — rejects if expired or tampered
- Exchanges `code` for tokens via Google token endpoint
- Extracts `refresh_token` (only present on first authorization; absent on
  re-auth if user already approved — handle by re-prompting with
  `prompt=consent&access_type=offline`)
- Fetches channel info (`youtube.channels.list me`) to get `channel_id` +
  `channel_title`
- Upserts `youtube_connections` row (encrypts refresh token before storing)
- Returns: `{"channel_id": "...", "channel_title": "..."}` — or redirects to
  frontend success page if `YOUTUBE_SUCCESS_REDIRECT_URL` is set

#### `GET /youtube/status`
- Requires: authenticated user
- Returns:
  - `{"connected": false}` if no row
  - `{"connected": true, "channel_id": "...", "channel_title": "..."}` if connected

#### `DELETE /youtube/disconnect`
- Requires: authenticated user
- Deletes `youtube_connections` row for current user
- Returns 204

---

## Upload job

### `POST /episodes/{episode_id}/upload`
- Requires: authenticated user, owns episode, `episode.status == "built"`,
  `episode.output_object_key` is set, YouTube connected
- Error if not built: 409 `{"detail": "ERR_EPISODE_NOT_BUILT"}`
- Error if not connected: 409 `{"detail": "ERR_YOUTUBE_NOT_CONNECTED"}`
- Creates `Job(episode_id=..., type="upload", status="queued")`
- Enqueues `upload_episode_task.delay(job_id)`
- Returns 202: `JobOut`

### Celery task: `upload_episode_task(job_id)`

```python
def run_upload(job_id: int, session_factory: sessionmaker) -> None:
    db = session_factory()
    job, episode = ...  # same pattern as run_build
    try:
        job.status = "running"; db.commit()

        connection = db.query(YouTubeConnection).filter_by(user_id=episode.user_id).one_or_none()
        if connection is None:
            raise RuntimeError("YouTube not connected")

        refresh_token = decrypt_token(connection.encrypted_refresh_token)
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )

        # Download output from S3 to temp file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            local_path = f.name
        try:
            download_to_path(episode.output_object_key, local_path)
            youtube = build("youtube", "v3", credentials=creds)
            body = {
                "snippet": {
                    "title": episode.title,
                    "description": episode.description,
                    "tags": [t.strip() for t in episode.tags.split(",") if t.strip()],
                },
                "status": {"privacyStatus": "private"},
            }
            media = MediaFileUpload(local_path, chunksize=-1, resumable=True)
            response = youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            ).execute()
            episode.youtube_video_id = response["id"]
        finally:
            os.unlink(local_path)

        episode.status = "uploaded"
        job.status = "done"; job.progress_pct = 100
        db.commit()
    except Exception as e:
        job.status = "failed"; job.error_message = str(e)
        episode.status = "built"  # revert so user can retry
        db.commit()
    finally:
        db.close()
```

### `Episode.youtube_video_id`

Add a nullable `youtube_video_id: Mapped[str | None]` column to `Episode`
so the frontend can link to `https://youtube.com/watch?v={id}` after upload.

---

## File structure

```
saas/
  models.py                    — add YouTubeConnection model, Episode.youtube_video_id
  schemas.py                   — add YouTubeStatusOut, YouTubeConnectOut
  youtube_auth.py              — NEW: encrypt/decrypt, build OAuth flow, fetch channel info
  tasks.py                     — add run_upload(), upload_episode_task Celery task
  routers/
    youtube.py                 — NEW: /youtube/* endpoints
  main.py                      — include youtube router
tests/saas/
  test_youtube_routes.py       — NEW: OAuth + status + disconnect + upload trigger tests
  test_youtube_task.py         — NEW: run_upload task tests (mock YouTube API + moto S3)
```

`agent_video/youtube_uploader.py` is NOT modified — it remains the CLI path.

---

## Dependencies

- `cryptography>=42.0.0` — for Fernet (add to `requirements.txt`)
- `google-auth>=2.0.0`, `google-auth-oauthlib>=1.2.0`, `google-api-python-client>=2.100.0`
  — already in `requirements.txt`

---

## Environment variables (add to `.env.example`)

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/youtube/callback
TOKEN_ENCRYPTION_KEY=   # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Security notes

- Refresh token encrypted at rest (Fernet AES-128-CBC + HMAC-SHA256)
- OAuth `state` is a signed JWT — prevents CSRF on the callback
- Upload always sets `privacyStatus: private` (user can change on YouTube later)
- `GOOGLE_CLIENT_ID/SECRET` never exposed to frontend

---

## Out of scope

- Re-uploading (changing title/privacy after first upload)
- Progress reporting during upload (job.progress_pct stays 0 until done)
- Token refresh auto-retry on 401 (google-auth library handles this transparently via `creds.refresh()`)
- Revoking the Google OAuth grant server-side on disconnect (just deletes our row)
