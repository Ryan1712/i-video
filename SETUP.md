# Setup (one-time)

## 1. ElevenLabs (voice)
1. Go to https://elevenlabs.io, sign in, open Settings → API Keys.
2. Create an API key, copy it into `.env` as `ELEVENLABS_API_KEY=...`.
3. Pick a voice (or clone your own) under Voices, copy its Voice ID into `.env` as `ELEVENLABS_VOICE_ID=...`.

## 2. YouTube (upload)
1. Go to https://console.cloud.google.com, create a new project.
2. Under "APIs & Services" → "Library", search for "YouTube Data API v3" and enable it.
3. Under "APIs & Services" → "Credentials", create an "OAuth Client ID" of type "Desktop app".
4. Download the resulting JSON and save it as `client_secret.json` in this project's root folder.
5. The first time you run `python -m agent_video upload <video_dir>`, a browser window opens asking you to log in and approve access — do this once. A token is cached afterward so you won't need to repeat this step.

## 3. Install dependencies
```
pip install -r requirements.txt
```

## 4. Try it
```
python -m agent_video new "What If The Moon Disappeared"
# edit videos/ep01_.../script.md, add required images to its assets/ folder
python -m agent_video status videos/ep01_what-if-the-moon-disappeared
python -m agent_video build videos/ep01_what-if-the-moon-disappeared
python -m agent_video upload videos/ep01_what-if-the-moon-disappeared
```

## 5. SaaS foundation (API + DB + background jobs)

1. Start Postgres and Redis: `docker compose up -d`
2. Copy the new variables from `.env.example` into `.env`: `DATABASE_URL`, `JWT_SECRET` (use a long random string), `REDIS_URL`.
3. Create the database tables (one-time, until a real migration tool is introduced):
   ```
   py -c "from saas.db import Base, init_session_factory; Base.metadata.create_all(init_session_factory().kw['bind'])"
   ```
4. Start the API: `py -m uvicorn saas.main:app --reload`
5. Start a Celery worker (separate terminal): `py -m celery -A saas.celery_app.celery_app worker --loglevel=info --pool=solo`
6. Start MinIO (already included in the `docker compose up -d` from step 1) and copy the new variables from `.env.example` into `.env`: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`. The bucket is created automatically on API/worker startup — no manual `mc` setup needed. The MinIO console is at http://localhost:9001 (login with `S3_ACCESS_KEY`/`S3_SECRET_KEY`) if you want to browse uploaded objects.
7. Open http://127.0.0.1:8000/docs for interactive API docs (signup, create an episode, upload assets per scene, trigger a build, poll `/jobs/{id}`).
8. AI features (script analysis, image generation, TTS) read these env vars — copy the ones you need from `.env.example` into `.env`:
   - `ANTHROPIC_API_KEY` — required for AI features (script analysis / scene splitting).
   - `ANTHROPIC_MODEL` — optional, defaults to `claude-sonnet-5`.
   - `OPENAI_API_KEY` — required for AI image generation.
   - `IMAGE_PROVIDER` / `IMAGE_MODEL` / `IMAGE_SIZE` — optional, default to `gpt-image` / `gpt-image-1` / `1536x1024`.
   - `TTS_PROVIDER` — optional, defaults to `elevenlabs` (set to `azure` to use Azure Speech instead).
   - `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` — optional, only needed when `TTS_PROVIDER=azure`.
   - `ELEVENLABS_COMPARE_VOICES` — optional, used by the voice comparison script.

## 6. Billing (Stripe + VN bank transfer)

1. Create a [Stripe](https://dashboard.stripe.com/test/apikeys) test-mode account, copy the **Secret key** into `STRIPE_SECRET_KEY`.
2. Create a webhook endpoint (Stripe CLI for local dev: `stripe listen --forward-to localhost:8000/billing/webhooks/stripe`), copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
3. Set `BANK_WEBHOOK_SECRET` to a long random string; configure your bank-transfer gateway (SePay/Casso) to send that value in the `x-webhook-secret` header when calling `POST /billing/webhooks/bank`.
4. Plans are created via `POST /admin/plans` (see section 7 below), which auto-syncs the matching Stripe Product/Price.

## 7. Admin panel (plans, vouchers, transactions, users, settings, audit log)

1. All `/admin/*` routes require a JWT for a user whose `role` column is `admin` — promote a user by setting `role='admin'` directly in the `users` table (no self-service promotion endpoint exists, by design).
2. Creating or updating a plan via `POST/PATCH /admin/plans` automatically creates/updates the matching Stripe Product/Price using the same `STRIPE_SECRET_KEY` configured in section 6 — no manual Stripe dashboard work needed for v1.
3. Unmatched bank transfers show up at `GET /admin/transactions/unmatched`; link one to a pending order with `POST /admin/transactions/{transaction_id}/link/{order_id}`.
4. Every plan/voucher/transaction/user/setting change and every admin login is written to `audit_logs`; browse it at `GET /admin/audit` (filter by `actor_user_id`, `action`, `from_date`, `to_date`) or export with `GET /admin/audit/export.csv`.
5. Support widget IDs (Messenger Page ID, Zalo OA ID, Facebook page URL) are set via `PUT /admin/settings/{key}` — the frontend reads `GET /admin/settings` to decide which widgets to render.

## 8. YouTube OAuth Setup (SaaS web flow)

This connects a user's YouTube channel so the API can upload videos on their behalf.

### 8.1 Create a Google Cloud project

1. Go to https://console.cloud.google.com and create a new project (or reuse an existing one).
2. Under **APIs & Services → Library**, search for **YouTube Data API v3** and click **Enable**.

### 8.2 Create OAuth 2.0 credentials

1. Under **APIs & Services → Credentials**, click **Create Credentials → OAuth client ID**.
2. Choose **Web application** as the application type.
3. Under **Authorized redirect URIs**, add the exact value you will set for `GOOGLE_OAUTH_REDIRECT_URI` (e.g. `http://localhost:8000/youtube/callback` for local dev).
   - This URI must match **exactly** — scheme, host, port, and path — otherwise Google will reject the OAuth callback.
4. Click **Create**, then copy the **Client ID** and **Client Secret** shown.

### 8.3 Set environment variables

Add the following to your `.env` file (values from step 8.2):

```
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/youtube/callback
TOKEN_ENCRYPTION_KEY=<generate-with-command-below>
```

Generate `TOKEN_ENCRYPTION_KEY` (Fernet symmetric key — run once, keep secret):

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 8.4 Connect a channel

1. Call `GET /youtube/connect` (authenticated) — returns a Google OAuth URL.
2. Open that URL in a browser, sign in, and approve access.
3. Google redirects to `GOOGLE_OAUTH_REDIRECT_URI`; the API exchanges the code for tokens and stores them encrypted.
4. Verify the connection with `GET /youtube/status`.
5. To disconnect: `DELETE /youtube/disconnect`.

Once connected, episode upload jobs (`POST /episodes/{id}/upload`) will push the rendered video to YouTube automatically.
