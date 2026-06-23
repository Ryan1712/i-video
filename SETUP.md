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
6. Open http://127.0.0.1:8000/docs for interactive API docs (signup, create an episode, upload assets per scene, trigger a build, poll `/jobs/{id}`).

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
