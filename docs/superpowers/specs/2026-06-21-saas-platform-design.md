# What If SaaS Platform — Design Spec

## Context
What started as a personal CLI tool for one YouTube channel grew, during design discussion, into a multi-tenant SaaS product the user wants to potentially sell: multiple users, subscription plans, billing (card + Vietnamese bank transfer), an admin panel, audit logging, multi-language UI (EN/VI), and embeddable support chat widgets (Messenger/Zalo/Facebook). The core video-generation engine (script → voice → Ken Burns video → YouTube upload) is specified separately in `2026-06-21-video-engine-design.md` and is reused here unchanged as the payload executed by a background worker — this spec covers everything *around* that engine: accounts, money, admin control, and the web UI.

This is intentionally a large, multi-subsystem spec by the user's explicit choice (they want the full architecture designed before building anything), but implementation should still proceed in phases — this doc describes the target architecture; the `writing-plans` step that follows will sequence the build.

## Architecture overview
```
┌─────────────┐      HTTPS/REST       ┌──────────────────┐
│  Frontend   │ ───────────────────►  │   FastAPI (API)   │
│  (React)    │ ◄───────────────────  │  auth/episodes/    │
│  i18n EN/VI │                       │  billing/admin      │
└─────────────┘                       └─────────┬─────────┘
                                                  │ enqueue job
                                                  ▼
                                       ┌──────────────────┐
                                       │  Redis (queue)    │
                                       └─────────┬─────────┘
                                                  ▼
                                       ┌──────────────────┐
                                       │ Celery worker(s)  │
                                       │ = video engine     │
                                       │ (see engine spec)  │
                                       └─────────┬─────────┘
                                                  ▼
                                       ┌──────────────────┐      ┌──────────────────┐
                                       │ Object storage     │      │   PostgreSQL       │
                                       │ (S3-compatible)    │◄────►│ users/plans/orders/ │
                                       └──────────────────┘      │ episodes/jobs/...    │
                                                                  └──────────────────┘
```

**Why this shape:** the video engine's logic (TTS, Ken Burns, ffmpeg, YouTube upload) doesn't change — it runs inside a Celery worker instead of a terminal. The API's job is account/billing/admin concerns and handing off build/upload work as queued jobs so one user's multi-minute video render never blocks another user's request.

**Stack decisions and why:**
- **Backend: FastAPI (Python), one codebase for API + engine.** The engine must run in Python regardless (ffmpeg orchestration, ElevenLabs, Pillow, YouTube API); a Node/other-language API would need a separate Python service plus an integration layer between them — strictly more moving parts for no quality gain.
- **DB: PostgreSQL.** Standard for relational data with subscriptions/billing integrity needs (transactions, foreign keys).
- **Payments: Stripe (cards) + SePay/Casso (VN bank transfer reconciliation).** See Billing section.
- **Job queue: Celery + Redis.** Video builds take minutes; queuing keeps the API responsive under concurrent users and lets worker capacity scale independently.
- **Storage: S3-compatible object storage** (e.g. Cloudflare R2 in production, MinIO for local dev). Required for multi-user file durability — local disk doesn't survive server replacement and doesn't scale across workers.
- **Auth: self-built JWT + `users` table.** No per-seat third-party auth fees; full control over the role/permission model billing depends on.
- **Frontend: React SPA** with `react-i18next` for EN/VI.
- **Deployment:** local/dev first (Docker-Compose-able from day one: api, worker, redis, postgres, minio services), production hosting decided later.

## Data model

```
users
  id, email, password_hash, role (user|admin), locale (en|vi),
  has_used_trial (bool), created_at

plans
  id, name, price_cents, currency, billing_interval, stripe_price_id,
  trial_days, limits (jsonb, e.g. {"episodes_per_month": 3}), created_at

subscriptions
  id, user_id, plan_id, stripe_subscription_id (nullable, null if bank-transfer-only),
  status (trialing|active|past_due|canceled), current_period_end

orders
  id, user_id, plan_id, amount, currency, payment_method (card|bank_transfer),
  status (pending|paid|failed|expired), unique_code, voucher_id (nullable),
  created_at, paid_at

vouchers
  id, code, discount_type (percent|fixed), discount_value, max_uses, used_count,
  expires_at, applicable_plan_ids (jsonb)

bank_transactions
  id, gateway_transaction_id (unique), amount, content, received_at,
  matched_order_id (nullable), status (matched|unmatched)

episodes
  id, user_id, title, description, tags, status (draft|ready|building|built|uploaded),
  created_at

scenes
  id, episode_id, order_index, asset_object_key, narration_text

jobs
  id, episode_id, type (build|upload), status (queued|running|done|failed),
  progress_pct, error_message, created_at

youtube_connections
  id, user_id, oauth_refresh_token (encrypted), channel_id

site_settings
  key, value   -- key-value store, e.g. messenger_page_id, zalo_oa_id, support widget toggles

audit_logs
  id, actor_user_id, actor_role, action, target_type, target_id,
  before_data (jsonb), after_data (jsonb), ip_address, created_at
  -- append-only: no UPDATE/DELETE in application code paths
```

Notes:
- `scenes` replaces reading `script.md` from disk — episode content lives in the DB; the web form edits scenes directly. `asset_object_key` points into object storage instead of a local `assets/` folder.
- `jobs` is how the frontend tracks build/upload progress (poll `GET /jobs/{id}` for `progress_pct`; upgrade to WebSocket later if polling proves insufficient — not needed for v1).
- Plan limits (`limits` jsonb) are enforced in the API before creating a new episode or queuing a build job, returning a translatable error code (`ERR_PLAN_LIMIT_REACHED`) on violation.

## Billing

### Card payments (Stripe)
1. User picks a plan → API creates a Stripe Checkout Session for that plan's `stripe_price_id` → user is redirected to Stripe-hosted checkout (card data never touches our servers).
2. Stripe webhooks drive state:
   - `checkout.session.completed` → activate subscription.
   - `invoice.payment_succeeded` → renew, update `current_period_end`.
   - `invoice.payment_failed` → mark `past_due`, restrict new-episode/build actions until resolved.
   - `customer.subscription.deleted` → downgrade to free/limited plan.
3. "Manage billing" in the user UI opens the Stripe Billing Portal (no custom UI needed for card updates/invoice history).

### Bank transfer (VN), with auto-reconciliation
1. Choosing "bank transfer" creates an `orders` row (`status=pending`) with a unique, never-reused `unique_code`.
2. A VietQR code is shown with the amount and `unique_code` pre-filled into the transfer content, minimizing user typos.
3. SePay/Casso watches the bank account and webhooks the backend on every incoming transaction; each is logged immutably in `bank_transactions` first (keyed by the gateway's own transaction id, for idempotency against webhook retries).
4. The backend parses `unique_code` from the transaction content and looks for a matching `pending` order with the **same amount**. Both must match to auto-approve — amount mismatch or unparseable content routes the transaction to an admin "Transactions needing review" screen instead of auto-crediting.
5. A matched, paid order activates/renews the subscription through the same code path Stripe success uses (one activation function, two payment-method entry points).
6. `pending` orders not paid within 30 minutes auto-expire (configurable in `site_settings`) to avoid a late/stale transfer being misattributed.
7. The webhook endpoint verifies the gateway's signature/secret; unsigned or invalid-signature calls are rejected.

### Vouchers
- `vouchers` table; for card payments, mapped to a Stripe Promotion Code so Stripe applies the discount at Checkout. For bank transfer, the backend discounts `orders.amount` before generating the QR. Expiry/usage-limit/applicable-plan checks happen before any discount is applied, returning translatable error codes on failure.

### Free trial
- Per-plan `trial_days`; no card required to start. A banner/email warns before expiry; on expiry without payment, the user is downgraded to the free plan (not locked out, no data loss). `has_used_trial` on `users` prevents repeat trials per account.

## Admin capabilities
- **Plan management UI**: admin creates/edits plans (name, price, limits, trial days); saving a plan syncs a Stripe Product/Price automatically (`stripe_price_id` stored back). Price changes create a *new* Stripe Price rather than mutating an existing one — Stripe doesn't allow changing the amount on an existing Price, and existing subscribers should keep their original price until they explicitly change plans.
- **Manual transaction review**: list of `bank_transactions` with `status=unmatched`; admin can manually link one to a pending order to approve it.
- **User management**: list users, current plan, suspend/unsuspend.
- **Support widget settings**: a settings page backed by `site_settings` for Messenger Page ID, Zalo OA ID, Facebook page URL, with a per-channel on/off toggle. Brand icons themselves ship as static frontend assets (official logos — not something admins should re-skin); only the underlying IDs/links are configurable, since those are account-specific and will differ per deployment/customer.
- **Audit log viewer**: searchable/filterable by actor, action type, date range; CSV export. Every sensitive action (plan changes, manual transaction approval, role changes, voucher CRUD, refunds, admin logins) is written here, unconditionally — not behind a feature flag.

## Internationalization (EN/VI)
- Frontend: `react-i18next`, all UI strings in `en.json`/`vi.json`, language switcher in the header.
- Backend: `users.locale` drives the language of transactional emails (welcome, invoice, trial-ending). API errors return stable codes (`ERR_PLAN_LIMIT_REACHED`, `ERR_VOUCHER_EXPIRED`, etc.); the frontend owns translating codes to user-facing text, so backend and frontend copy never drift out of sync.
- User-generated content (episode titles/descriptions) is stored and shown as-authored — no auto-translation in v1.

## Support chat widgets
Official Messenger Customer Chat and Zalo OA embeddable widgets, rendered only when the corresponding `site_settings` ID is configured; each channel independently toggleable.

## Out of scope for this spec (deferred)
- Word-level/karaoke captions (engine spec already scopes this out for v1).
- WebSocket-based live job progress (start with polling).
- Multi-currency beyond VND/USD unless a concrete need arises.
- Production deployment topology (domains, SSL, CI/CD) — to be addressed when first deploying past local/dev.

## Verification
Given the size of this spec, verification is per-subsystem at implementation time (covered in the implementation plan), but at minimum before considering the platform usable end-to-end:
1. A new user can sign up, start a trial, create an episode via the web form, upload images, trigger a build job, see progress, preview the result, and connect/upload to their own YouTube channel.
2. A user can subscribe via Stripe test mode and via a simulated bank-transfer webhook payload, and see their plan limits enforced correctly in both cases.
3. An admin can create a plan (verifying it appears correctly in Stripe), manually approve an unmatched bank transaction, and see both actions reflected in the audit log with correct before/after data.
4. Switching the language toggle changes all UI strings and the language of a triggered transactional email.
