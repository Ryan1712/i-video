# Billing Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add subscription billing to the `saas` backend — Stripe card checkout, Vietnamese bank-transfer with auto-reconciliation, vouchers, free trials, and plan-limit enforcement — reusing the `saas-foundation` auth/episode code already merged to `master`.

**Architecture:** New `saas/billing/` package holds a thin Stripe client wrapper and a payment-method-agnostic `activate_subscription`/`renew_subscription` service used by both the Stripe webhook and the bank-transfer reconciliation webhook (per spec: "one activation function, two payment-method entry points"). New ORM models (`Plan`, `Subscription`, `Order`, `Voucher`, `BankTransaction`) extend `saas/models.py`. New routes live in `saas/routers/billing.py`. Plan-limit enforcement is a small dependency reused by the existing `episodes` router.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, `stripe` Python SDK, Pydantic v2. No new infra (no Celery beat, no cron) — trial/order expiry are checked lazily on read, matching YAGNI.

## Global Constraints

- Reuse the existing `saas/db.py` `Base`, `get_db`, session-factory pattern — do not create a second DB setup.
- Reuse the existing `saas/deps.py` `get_current_user` — do not create a second auth mechanism.
- All new DB writes that mutate money/subscription state must be auditable: store `before`/`after` status transitions are out of scope for this plan (full `audit_logs` table is the Admin plan's job per spec) but every state-changing function must be a single, named, testable function — no inline status mutation scattered across routes.
- Money amounts are stored as integer cents (`amount_cents`), never floats.
- Tests use the existing `tests/saas/conftest.py` SQLite fixtures (`db_session_factory`, `db_session`) — do not create a second test-DB fixture file. Do **not** create a `tests/saas/__init__.py` (it shadows the real `saas` package under pytest's import mode — this bit a previous task and the fix was to delete it).
- Stripe and SePay/Casso calls are mocked in tests — no real network calls in the test suite.
- Stable, translatable error codes from the spec must be used verbatim: `ERR_PLAN_LIMIT_REACHED`, `ERR_VOUCHER_EXPIRED`, `ERR_VOUCHER_INVALID`, `ERR_ORDER_EXPIRED`.

---

## File Structure

- Create: `saas/billing/__init__.py` — empty package marker.
- Create: `saas/billing/stripe_client.py` — thin wrapper around the `stripe` SDK (`create_checkout_session`, `construct_webhook_event`). Isolated so tests mock this module, never the real SDK.
- Create: `saas/billing/service.py` — payment-method-agnostic logic: `activate_subscription`, `renew_subscription`, `mark_past_due`, `downgrade_subscription`, `validate_voucher`, `apply_voucher_discount`, `expire_stale_orders`.
- Create: `saas/routers/billing.py` — `POST /billing/checkout`, `POST /billing/webhooks/stripe`, `POST /billing/orders/bank-transfer`, `POST /billing/webhooks/bank`, `GET /billing/subscription`.
- Modify: `saas/models.py` — add `Plan`, `Subscription`, `Order`, `Voucher`, `BankTransaction`.
- Modify: `saas/schemas.py` — add billing request/response models.
- Modify: `saas/main.py` — register `billing.router`.
- Modify: `saas/routers/episodes.py` — add plan-limit check to `create_episode`.
- Modify: `requirements.txt` — add `stripe`.
- Modify: `.env.example` — add `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `BANK_WEBHOOK_SECRET`.
- Modify: `SETUP.md` — document Stripe test-mode setup and bank-webhook secret.
- Test: `tests/saas/test_billing_models.py`, `tests/saas/test_billing_service.py`, `tests/saas/test_billing_checkout.py`, `tests/saas/test_billing_stripe_webhook.py`, `tests/saas/test_billing_bank_transfer.py`, `tests/saas/test_billing_bank_webhook.py`, `tests/saas/test_billing_vouchers.py`, `tests/saas/test_plan_limits.py`.

---

### Task 1: Billing data model

**Files:**
- Modify: `saas/models.py`
- Modify: `requirements.txt`
- Test: `tests/saas/test_billing_models.py`

**Interfaces:**
- Produces: `Plan(id, name, price_cents, currency, billing_interval, stripe_price_id, trial_days, limits, created_at)`, `Subscription(id, user_id, plan_id, stripe_subscription_id, status, current_period_end, created_at)`, `Order(id, user_id, plan_id, amount_cents, currency, payment_method, status, unique_code, voucher_id, created_at, paid_at)`, `Voucher(id, code, discount_type, discount_value, max_uses, used_count, expires_at, applicable_plan_ids, created_at)`, `BankTransaction(id, gateway_transaction_id, amount_cents, content, received_at, matched_order_id, status, created_at)`. Also adds `User.has_used_trial: bool` (spec field, was missing from `saas-foundation`).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_models.py
import datetime

from saas.models import BankTransaction, Order, Plan, Subscription, User, Voucher


def test_plan_round_trip(db_session):
    plan = Plan(
        name="Pro", price_cents=199000, currency="VND", billing_interval="month",
        stripe_price_id="price_test_123", trial_days=7, limits={"episodes_per_month": 10},
    )
    db_session.add(plan)
    db_session.commit()

    fetched = db_session.query(Plan).filter_by(name="Pro").one()
    assert fetched.price_cents == 199000
    assert fetched.limits == {"episodes_per_month": 10}


def test_subscription_links_user_and_plan(db_session):
    user = User(email="a@x.com", password_hash="h")
    plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    sub = Subscription(user_id=user.id, plan_id=plan.id, status="trialing")
    db_session.add(sub)
    db_session.commit()

    fetched = db_session.query(Subscription).one()
    assert fetched.user_id == user.id
    assert fetched.plan_id == plan.id
    assert fetched.status == "trialing"


def test_order_and_voucher(db_session):
    user = User(email="b@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    voucher = Voucher(code="SALE10", discount_type="percent", discount_value=10, max_uses=100, applicable_plan_ids=[plan.id])
    db_session.add(voucher)
    db_session.commit()

    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=179100, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-ABC123", voucher_id=voucher.id,
    )
    db_session.add(order)
    db_session.commit()

    fetched = db_session.query(Order).one()
    assert fetched.voucher_id == voucher.id
    assert fetched.unique_code == "OID-ABC123"


def test_bank_transaction_unique_gateway_id(db_session):
    txn = BankTransaction(
        gateway_transaction_id="GW-1", amount_cents=179100, content="OID-ABC123 payment",
        received_at=datetime.datetime.utcnow(), status="unmatched",
    )
    db_session.add(txn)
    db_session.commit()

    fetched = db_session.query(BankTransaction).one()
    assert fetched.status == "unmatched"
    assert fetched.matched_order_id is None


def test_user_has_used_trial_defaults_false(db_session):
    user = User(email="c@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    assert db_session.query(User).one().has_used_trial is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Plan' from 'saas.models'`

- [ ] **Step 3: Implement the models**

Add to `saas/models.py` (after the existing imports, add `Boolean, JSON`; after the `User` class, add `has_used_trial`; then append the five new classes at the end of the file):

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
```//replace the existing import line with this one (adds Boolean, JSON)

Add this field inside `class User`, right after `role`:

```python
    has_used_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Append at the end of `saas/models.py`:

```python
class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="VND")
    billing_interval: Mapped[str] = mapped_column(String(20), nullable=False, default="month")
    stripe_price_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trialing")
    current_period_end: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="VND")
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    unique_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    voucher_id: Mapped[int | None] = mapped_column(ForeignKey("vouchers.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    paid_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class Voucher(Base):
    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    applicable_plan_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gateway_transaction_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    matched_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

Add `stripe>=9.0.0` to `requirements.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_models.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/models.py requirements.txt tests/saas/test_billing_models.py
git commit -m "feat(billing): add Plan/Subscription/Order/Voucher/BankTransaction models"
```

---

### Task 2: Stripe client wrapper

**Files:**
- Create: `saas/billing/__init__.py`
- Create: `saas/billing/stripe_client.py`
- Test: `tests/saas/test_billing_stripe_client.py`

**Interfaces:**
- Consumes: `os.environ["STRIPE_SECRET_KEY"]`, `os.environ["STRIPE_WEBHOOK_SECRET"]`.
- Produces: `create_checkout_session(price_id: str, success_url: str, cancel_url: str, customer_email: str, promotion_code: str | None = None) -> stripe.checkout.Session`, `construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event`, `get_stripe_secret_key() -> str`, `get_stripe_webhook_secret() -> str` (both raise `RuntimeError` if unset, mirroring `saas/security.py`'s `get_jwt_secret`).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_stripe_client.py
from unittest.mock import MagicMock, patch

import pytest

from saas.billing.stripe_client import (
    construct_webhook_event,
    create_checkout_session,
    get_stripe_secret_key,
    get_stripe_webhook_secret,
)


def test_get_stripe_secret_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        get_stripe_secret_key()


def test_get_stripe_webhook_secret_raises_when_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        get_stripe_webhook_secret()


@patch("saas.billing.stripe_client.stripe.checkout.Session.create")
def test_create_checkout_session_calls_stripe_sdk(mock_create, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    mock_create.return_value = MagicMock(id="cs_test_1", url="https://checkout.stripe.com/cs_test_1")

    session = create_checkout_session(
        price_id="price_123", success_url="https://app/success", cancel_url="https://app/cancel",
        customer_email="user@x.com",
    )

    assert session.id == "cs_test_1"
    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert kwargs["customer_email"] == "user@x.com"
    assert kwargs["mode"] == "subscription"


@patch("saas.billing.stripe_client.stripe.Webhook.construct_event")
def test_construct_webhook_event_calls_stripe_sdk(mock_construct, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_123")
    mock_construct.return_value = {"type": "checkout.session.completed"}

    event = construct_webhook_event(b"payload", "sig_header_value")

    assert event["type"] == "checkout.session.completed"
    mock_construct.assert_called_once_with(b"payload", "sig_header_value", "whsec_123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_stripe_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.billing'`

- [ ] **Step 3: Implement**

`saas/billing/__init__.py`: empty file.

```python
# saas/billing/stripe_client.py
"""Thin wrapper around the Stripe SDK so the rest of the app never imports `stripe` directly."""
from __future__ import annotations

import os

import stripe


def get_stripe_secret_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")
    return key


def get_stripe_webhook_secret() -> str:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET environment variable is not set")
    return secret


def create_checkout_session(
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    promotion_code: str | None = None,
) -> stripe.checkout.Session:
    stripe.api_key = get_stripe_secret_key()
    kwargs = dict(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
    )
    if promotion_code:
        kwargs["discounts"] = [{"promotion_code": promotion_code}]
    return stripe.checkout.Session.create(**kwargs)


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    secret = get_stripe_webhook_secret()
    return stripe.Webhook.construct_event(payload, sig_header, secret)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_stripe_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/__init__.py saas/billing/stripe_client.py tests/saas/test_billing_stripe_client.py
git commit -m "feat(billing): add Stripe client wrapper"
```

---

### Task 3: Shared activation/renewal service + voucher validation

**Files:**
- Create: `saas/billing/service.py`
- Test: `tests/saas/test_billing_service.py`

**Interfaces:**
- Consumes: `Plan`, `Subscription`, `Order`, `Voucher`, `BankTransaction`, `User` from `saas.models` (Task 1).
- Produces: `activate_subscription(db: Session, order: Order) -> Subscription`, `renew_subscription(db: Session, subscription: Subscription, new_period_end: datetime.datetime) -> Subscription`, `mark_past_due(db: Session, subscription: Subscription) -> Subscription`, `downgrade_to_free(db: Session, subscription: Subscription, free_plan: Plan) -> Subscription`, `validate_voucher(db: Session, code: str, plan_id: int) -> Voucher` (raises `VoucherError(code: str)` with `.code` in `{"ERR_VOUCHER_EXPIRED", "ERR_VOUCHER_INVALID"}`), `apply_voucher_discount(amount_cents: int, voucher: Voucher) -> int`, `expire_stale_orders(db: Session, max_age_minutes: int = 30) -> int` (returns count expired).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_service.py
import datetime

import pytest

from saas.billing.service import (
    VoucherError,
    activate_subscription,
    apply_voucher_discount,
    downgrade_to_free,
    expire_stale_orders,
    mark_past_due,
    renew_subscription,
    validate_voucher,
)
from saas.models import Order, Plan, Subscription, User, Voucher


def _make_user_and_plan(db_session):
    user = User(email="u@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    return user, plan


def test_activate_subscription_creates_active_subscription(db_session):
    user, plan = _make_user_and_plan(db_session)
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-1",
    )
    db_session.add(order)
    db_session.commit()

    sub = activate_subscription(db_session, order)

    assert sub.user_id == user.id
    assert sub.plan_id == plan.id
    assert sub.status == "active"
    refreshed_order = db_session.query(Order).filter_by(id=order.id).one()
    assert refreshed_order.status == "paid"
    assert refreshed_order.paid_at is not None


def test_activate_subscription_reuses_existing_subscription_row(db_session):
    user, plan = _make_user_and_plan(db_session)
    existing = Subscription(user_id=user.id, plan_id=plan.id, status="past_due")
    db_session.add(existing)
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-2",
    )
    db_session.add(order)
    db_session.commit()

    sub = activate_subscription(db_session, order)

    assert sub.id == existing.id
    assert sub.status == "active"
    assert db_session.query(Subscription).count() == 1


def test_renew_subscription_updates_period_end(db_session):
    user, plan = _make_user_and_plan(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active")
    db_session.add(sub)
    db_session.commit()

    new_end = datetime.datetime(2026, 7, 1)
    renewed = renew_subscription(db_session, sub, new_end)

    assert renewed.current_period_end == new_end
    assert renewed.status == "active"


def test_mark_past_due(db_session):
    user, plan = _make_user_and_plan(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active")
    db_session.add(sub)
    db_session.commit()

    updated = mark_past_due(db_session, sub)
    assert updated.status == "past_due"


def test_downgrade_to_free(db_session):
    user, plan = _make_user_and_plan(db_session)
    free_plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add(free_plan)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="past_due")
    db_session.add(sub)
    db_session.commit()

    updated = downgrade_to_free(db_session, sub, free_plan)
    assert updated.plan_id == free_plan.id
    assert updated.status == "active"


def test_validate_voucher_rejects_expired(db_session):
    _, plan = _make_user_and_plan(db_session)
    voucher = Voucher(
        code="OLD10", discount_type="percent", discount_value=10, max_uses=10,
        expires_at=datetime.datetime(2020, 1, 1), applicable_plan_ids=[plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "OLD10", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_EXPIRED"


def test_validate_voucher_rejects_unknown_code(db_session):
    _, plan = _make_user_and_plan(db_session)
    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "NOPE", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_validate_voucher_rejects_wrong_plan(db_session):
    _, plan = _make_user_and_plan(db_session)
    other_plan = Plan(name="Other", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add(other_plan)
    db_session.commit()
    voucher = Voucher(
        code="ONLYOTHER", discount_type="percent", discount_value=10, max_uses=10,
        applicable_plan_ids=[other_plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "ONLYOTHER", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_validate_voucher_rejects_exhausted(db_session):
    _, plan = _make_user_and_plan(db_session)
    voucher = Voucher(
        code="USED", discount_type="percent", discount_value=10, max_uses=1, used_count=1,
        applicable_plan_ids=[plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "USED", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_apply_voucher_discount_percent():
    voucher = Voucher(code="P10", discount_type="percent", discount_value=10, applicable_plan_ids=[])
    assert apply_voucher_discount(100000, voucher) == 90000


def test_apply_voucher_discount_fixed():
    voucher = Voucher(code="F5000", discount_type="fixed", discount_value=5000, applicable_plan_ids=[])
    assert apply_voucher_discount(100000, voucher) == 95000


def test_apply_voucher_discount_never_negative():
    voucher = Voucher(code="BIG", discount_type="fixed", discount_value=999999, applicable_plan_ids=[])
    assert apply_voucher_discount(1000, voucher) == 0


def test_expire_stale_orders(db_session):
    user, plan = _make_user_and_plan(db_session)
    stale = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=1000, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-OLD",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=45),
    )
    fresh = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=1000, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-NEW",
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add_all([stale, fresh])
    db_session.commit()

    count = expire_stale_orders(db_session, max_age_minutes=30)

    assert count == 1
    assert db_session.query(Order).filter_by(unique_code="OID-OLD").one().status == "expired"
    assert db_session.query(Order).filter_by(unique_code="OID-NEW").one().status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.billing.service'`

- [ ] **Step 3: Implement**

```python
# saas/billing/service.py
"""Payment-method-agnostic billing logic shared by the Stripe and bank-transfer flows."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from ..models import Order, Plan, Subscription, Voucher


class VoucherError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def activate_subscription(db: Session, order: Order) -> Subscription:
    subscription = (
        db.query(Subscription)
        .filter_by(user_id=order.user_id, plan_id=order.plan_id)
        .one_or_none()
    )
    if subscription is None:
        subscription = Subscription(user_id=order.user_id, plan_id=order.plan_id)
        db.add(subscription)

    subscription.status = "active"
    order.status = "paid"
    order.paid_at = datetime.datetime.utcnow()
    db.commit()
    return subscription


def renew_subscription(db: Session, subscription: Subscription, new_period_end: datetime.datetime) -> Subscription:
    subscription.status = "active"
    subscription.current_period_end = new_period_end
    db.commit()
    return subscription


def mark_past_due(db: Session, subscription: Subscription) -> Subscription:
    subscription.status = "past_due"
    db.commit()
    return subscription


def downgrade_to_free(db: Session, subscription: Subscription, free_plan: Plan) -> Subscription:
    subscription.plan_id = free_plan.id
    subscription.status = "active"
    db.commit()
    return subscription


def validate_voucher(db: Session, code: str, plan_id: int) -> Voucher:
    voucher = db.query(Voucher).filter_by(code=code).one_or_none()
    if voucher is None:
        raise VoucherError("ERR_VOUCHER_INVALID")
    if plan_id not in (voucher.applicable_plan_ids or []):
        raise VoucherError("ERR_VOUCHER_INVALID")
    if voucher.used_count >= voucher.max_uses:
        raise VoucherError("ERR_VOUCHER_INVALID")
    if voucher.expires_at is not None and voucher.expires_at < datetime.datetime.utcnow():
        raise VoucherError("ERR_VOUCHER_EXPIRED")
    return voucher


def apply_voucher_discount(amount_cents: int, voucher: Voucher) -> int:
    if voucher.discount_type == "percent":
        discount = amount_cents * voucher.discount_value // 100
    else:
        discount = voucher.discount_value
    return max(0, amount_cents - discount)


def expire_stale_orders(db: Session, max_age_minutes: int = 30) -> int:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=max_age_minutes)
    stale_orders = (
        db.query(Order)
        .filter(Order.status == "pending", Order.created_at < cutoff)
        .all()
    )
    for order in stale_orders:
        order.status = "expired"
    db.commit()
    return len(stale_orders)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_service.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/service.py tests/saas/test_billing_service.py
git commit -m "feat(billing): add activation/renewal service and voucher validation"
```

---

### Task 4: Billing schemas

**Files:**
- Modify: `saas/schemas.py`
- Test: covered by Task 5/6/7's route tests (no standalone schema test needed — Pydantic validation is exercised through the routes).

**Interfaces:**
- Produces: `CheckoutRequest(plan_id: int, voucher_code: str | None = None)`, `CheckoutResponse(checkout_url: str)`, `BankTransferRequest(plan_id: int, voucher_code: str | None = None)`, `BankTransferResponse(order_id: int, unique_code: str, amount_cents: int, bank_account_qr_payload: str)`, `SubscriptionOut(plan_id: int, status: str, current_period_end: datetime.datetime | None)`.

- [ ] **Step 1: Write the failing test**

This task has no new test file — it's exercised by Task 5–7 route tests, which will fail to import until these schemas exist. Confirm via:

Run: `py -c "from saas.schemas import CheckoutRequest"`
Expected: FAIL with `ImportError`

- [ ] **Step 2: (combined with Step 1 above — import check is the "test")**

- [ ] **Step 3: Implement**

Add to `saas/schemas.py` (add `import datetime` to the top, then append at the end of the file):

```python
class CheckoutRequest(BaseModel):
    plan_id: int
    voucher_code: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str


class BankTransferRequest(BaseModel):
    plan_id: int
    voucher_code: str | None = None


class BankTransferResponse(BaseModel):
    order_id: int
    unique_code: str
    amount_cents: int
    bank_account_qr_payload: str


class SubscriptionOut(BaseModel):
    plan_id: int
    status: str
    current_period_end: datetime.datetime | None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -c "from saas.schemas import CheckoutRequest, CheckoutResponse, BankTransferRequest, BankTransferResponse, SubscriptionOut"`
Expected: no output, exit code 0

- [ ] **Step 5: Commit**

```bash
git add saas/schemas.py
git commit -m "feat(billing): add checkout/bank-transfer/subscription schemas"
```

---

### Task 5: Stripe checkout + webhook routes

**Files:**
- Create: `saas/routers/billing.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_billing_checkout.py`, `tests/saas/test_billing_stripe_webhook.py`

**Interfaces:**
- Consumes: `create_checkout_session`, `construct_webhook_event` (Task 2); `activate_subscription`, `renew_subscription`, `mark_past_due`, `downgrade_to_free`, `validate_voucher`, `apply_voucher_discount`, `VoucherError` (Task 3); `CheckoutRequest`, `CheckoutResponse` (Task 4); `Plan`, `Order`, `Subscription` (Task 1); `get_current_user` (existing `saas/deps.py`).
- Produces: `router` (prefix `/billing`) with `POST /billing/checkout`, `POST /billing/webhooks/stripe`. Both reused by later tasks via the same `router` object.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_checkout.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from saas.db import Base, get_db
from saas.main import app
from saas.models import Plan, User
from saas.security import create_access_token, get_jwt_secret, hash_password


def _client_and_token(db_session_factory, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    user = User(email="buyer@x.com", password_hash=hash_password("pw"))
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    return client, token, user


@patch("saas.routers.billing.create_checkout_session")
def test_checkout_creates_session_and_returns_url(mock_create_session, db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", stripe_price_id="price_pro", trial_days=0, limits={})
    db_session.add(plan)
    db_session.commit()

    client, token, user = _client_and_token(db_session_factory, db_session)
    mock_create_session.return_value = MagicMock(url="https://checkout.stripe.com/cs_test_abc")

    response = client.post(
        "/billing/checkout",
        json={"plan_id": plan.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["checkout_url"] == "https://checkout.stripe.com/cs_test_abc"
    mock_create_session.assert_called_once()
    app.dependency_overrides.clear()


def test_checkout_requires_auth(db_session_factory, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    response = client.post("/billing/checkout", json={"plan_id": 1})

    assert response.status_code == 401
    app.dependency_overrides.clear()


def test_checkout_rejects_unknown_plan(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    client, token, user = _client_and_token(db_session_factory, db_session)

    response = client.post(
        "/billing/checkout",
        json={"plan_id": 999},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    app.dependency_overrides.clear()
```

```python
# tests/saas/test_billing_stripe_webhook.py
from unittest.mock import patch

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import Order, Plan, Subscription, User


def _setup(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    user = User(email="webhook@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", stripe_price_id="price_pro", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-STRIPE-1",
    )
    db_session.add(order)
    db_session.commit()
    return user, plan, order


@patch("saas.routers.billing.construct_webhook_event")
def test_checkout_completed_activates_subscription(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"order_id": str(order.id)}}},
    }
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    assert db_session.query(Subscription).filter_by(user_id=user.id).one().status == "active"
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_invoice_payment_failed_marks_past_due(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active", stripe_subscription_id="sub_123")
    db_session.add(sub)
    db_session.commit()

    mock_construct.return_value = {
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_123"}},
    }
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    assert db_session.query(Subscription).filter_by(id=sub.id).one().status == "past_due"
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_invalid_signature_rejected(mock_construct, db_session_factory, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    mock_construct.side_effect = ValueError("Invalid signature")
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "bad"},
    )

    assert response.status_code == 400
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_checkout.py tests/saas/test_billing_stripe_webhook.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.billing'`

- [ ] **Step 3: Implement**

```python
# saas/routers/billing.py
"""Billing routes: Stripe checkout/webhooks and bank-transfer orders/webhooks."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..billing.service import (
    VoucherError,
    activate_subscription,
    apply_voucher_discount,
    downgrade_to_free,
    mark_past_due,
    renew_subscription,
    validate_voucher,
)
from ..billing.stripe_client import construct_webhook_event, create_checkout_session
from ..db import get_db
from ..deps import get_current_user
from ..models import Order, Plan, Subscription, User
from ..schemas import CheckoutRequest, CheckoutResponse

router = APIRouter(prefix="/billing", tags=["billing"])


def _generate_unique_code(db: Session) -> str:
    import secrets

    while True:
        code = "OID-" + secrets.token_hex(6).upper()
        if db.query(Order).filter_by(unique_code=code).first() is None:
            return code


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    plan = db.query(Plan).filter_by(id=payload.plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    amount_cents = plan.price_cents
    promotion_code = None
    if payload.voucher_code:
        try:
            voucher = validate_voucher(db, payload.voucher_code, plan.id)
        except VoucherError as e:
            raise HTTPException(status_code=400, detail=e.code)
        amount_cents = apply_voucher_discount(amount_cents, voucher)
        promotion_code = payload.voucher_code

    order = Order(
        user_id=current_user.id, plan_id=plan.id, amount_cents=amount_cents, currency=plan.currency,
        payment_method="card", status="pending", unique_code=_generate_unique_code(db),
    )
    db.add(order)
    db.commit()

    session = create_checkout_session(
        price_id=plan.stripe_price_id,
        success_url="https://app.local/billing/success",
        cancel_url="https://app.local/billing/cancel",
        customer_email=current_user.email,
        promotion_code=promotion_code,
    )
    return CheckoutResponse(checkout_url=session.url)


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
    db: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    try:
        event = construct_webhook_event(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        order_id = int(data["metadata"]["order_id"])
        order = db.query(Order).filter_by(id=order_id).one()
        activate_subscription(db, order)
    elif event_type == "invoice.payment_succeeded":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["subscription"]).one()
        renew_subscription(db, sub, datetime.datetime.utcnow() + datetime.timedelta(days=30))
    elif event_type == "invoice.payment_failed":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["subscription"]).one()
        mark_past_due(db, sub)
    elif event_type == "customer.subscription.deleted":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["id"]).one()
        free_plan = db.query(Plan).filter_by(price_cents=0).first()
        if free_plan is not None:
            downgrade_to_free(db, sub, free_plan)

    return {"received": True}
```

Note: `checkout.session.completed` requires the Stripe Checkout Session to be created with `metadata={"order_id": str(order.id)}` — add that to `create_checkout_session`'s call in `checkout()` above (pass `metadata` through `stripe_client.create_checkout_session`). Update `saas/billing/stripe_client.py`'s `create_checkout_session` signature to accept `metadata: dict | None = None` and pass it through to `stripe.checkout.Session.create(**kwargs)` when present, and update the `checkout()` route to pass `metadata={"order_id": str(order.id)}`.

Update `saas/main.py`:

```python
from .routers import auth, billing, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_checkout.py tests/saas/test_billing_stripe_webhook.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/billing.py saas/billing/stripe_client.py saas/main.py tests/saas/test_billing_checkout.py tests/saas/test_billing_stripe_webhook.py
git commit -m "feat(billing): add Stripe checkout and webhook routes"
```

---

### Task 6: Bank-transfer order creation route

**Files:**
- Modify: `saas/routers/billing.py`
- Test: `tests/saas/test_billing_bank_transfer.py`

**Interfaces:**
- Consumes: `BankTransferRequest`, `BankTransferResponse` (Task 4); `_generate_unique_code` (Task 5, same file).
- Produces: `POST /billing/orders/bank-transfer` added to the existing `router`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_bank_transfer.py
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import Order, Plan, User
from saas.security import create_access_token


def test_bank_transfer_creates_pending_order_with_qr_payload(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", trial_days=0, limits={})
    user = User(email="bt@x.com", password_hash="h")
    db_session.add_all([plan, user])
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.post(
        "/billing/orders/bank-transfer",
        json={"plan_id": plan.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["amount_cents"] == 199000
    assert body["unique_code"].startswith("OID-")
    assert body["unique_code"] in body["bank_account_qr_payload"]

    order = db_session.query(Order).filter_by(id=body["order_id"]).one()
    assert order.status == "pending"
    assert order.payment_method == "bank_transfer"
    app.dependency_overrides.clear()


def test_bank_transfer_applies_voucher_discount(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    from saas.models import Voucher

    app.dependency_overrides[get_db] = lambda: db_session
    plan = Plan(name="Pro", price_cents=200000, currency="VND", billing_interval="month", trial_days=0, limits={})
    user = User(email="bt2@x.com", password_hash="h")
    db_session.add_all([plan, user])
    db_session.commit()
    voucher = Voucher(code="HALF", discount_type="percent", discount_value=50, max_uses=10, applicable_plan_ids=[plan.id])
    db_session.add(voucher)
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.post(
        "/billing/orders/bank-transfer",
        json={"plan_id": plan.id, "voucher_code": "HALF"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["amount_cents"] == 100000
    app.dependency_overrides.clear()


def test_bank_transfer_rejects_invalid_voucher(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    plan = Plan(name="Pro", price_cents=200000, currency="VND", billing_interval="month", trial_days=0, limits={})
    user = User(email="bt3@x.com", password_hash="h")
    db_session.add_all([plan, user])
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.post(
        "/billing/orders/bank-transfer",
        json={"plan_id": plan.id, "voucher_code": "NOPE"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "ERR_VOUCHER_INVALID"
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_bank_transfer.py -v`
Expected: FAIL with `404 Not Found` (route doesn't exist yet)

- [ ] **Step 3: Implement**

Add to `saas/schemas.py` import list nothing new (already added in Task 4). Append to `saas/routers/billing.py`:

```python
from ..schemas import BankTransferRequest, BankTransferResponse


@router.post("/orders/bank-transfer", response_model=BankTransferResponse)
def create_bank_transfer_order(
    payload: BankTransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BankTransferResponse:
    plan = db.query(Plan).filter_by(id=payload.plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    amount_cents = plan.price_cents
    if payload.voucher_code:
        try:
            voucher = validate_voucher(db, payload.voucher_code, plan.id)
        except VoucherError as e:
            raise HTTPException(status_code=400, detail=e.code)
        amount_cents = apply_voucher_discount(amount_cents, voucher)

    unique_code = _generate_unique_code(db)
    order = Order(
        user_id=current_user.id, plan_id=plan.id, amount_cents=amount_cents, currency=plan.currency,
        payment_method="bank_transfer", status="pending", unique_code=unique_code,
    )
    db.add(order)
    db.commit()

    qr_payload = f"bank:whatif|amount:{amount_cents}|content:{unique_code}"
    return BankTransferResponse(
        order_id=order.id, unique_code=unique_code, amount_cents=amount_cents,
        bank_account_qr_payload=qr_payload,
    )
```

Note: move the `from ..schemas import CheckoutRequest, CheckoutResponse` line at the top of the file into one combined import: `from ..schemas import BankTransferRequest, BankTransferResponse, CheckoutRequest, CheckoutResponse` (remove the duplicate added above).

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_bank_transfer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/billing.py tests/saas/test_billing_bank_transfer.py
git commit -m "feat(billing): add bank-transfer order creation route"
```

---

### Task 7: Bank-transaction reconciliation webhook

**Files:**
- Modify: `saas/routers/billing.py`
- Create: `saas/billing/bank_webhook_secret.py` — actually fold into `stripe_client.py`-style helper inside `service.py`; see Step 3.
- Test: `tests/saas/test_billing_bank_webhook.py`

**Interfaces:**
- Consumes: `BankTransaction`, `Order` (Task 1); `activate_subscription` (Task 3).
- Produces: `POST /billing/webhooks/bank` added to `router`; `get_bank_webhook_secret() -> str` in `saas/billing/service.py` (raises `RuntimeError` if `BANK_WEBHOOK_SECRET` unset, same pattern as `get_jwt_secret`).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_bank_webhook.py
import datetime

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import BankTransaction, Order, Plan, Subscription, User


def _setup_order(db_session, amount_cents=199000, unique_code="OID-BANK-1"):
    user = User(email="bank@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=amount_cents, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=amount_cents, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code=unique_code,
    )
    db_session.add(order)
    db_session.commit()
    return user, plan, order


def test_matching_transaction_activates_subscription(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("BANK_WEBHOOK_SECRET", "bank-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user, plan, order = _setup_order(db_session)
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/bank",
        json={
            "gateway_transaction_id": "GW-1", "amount_cents": 199000,
            "content": f"chuyen tien {order.unique_code}", "received_at": datetime.datetime.utcnow().isoformat(),
        },
        headers={"x-webhook-secret": "bank-secret"},
    )

    assert response.status_code == 200
    refreshed_order = db_session.query(Order).filter_by(id=order.id).one()
    assert refreshed_order.status == "paid"
    txn = db_session.query(BankTransaction).filter_by(gateway_transaction_id="GW-1").one()
    assert txn.status == "matched"
    assert txn.matched_order_id == order.id
    assert db_session.query(Subscription).filter_by(user_id=user.id).one().status == "active"
    app.dependency_overrides.clear()


def test_amount_mismatch_leaves_transaction_unmatched(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("BANK_WEBHOOK_SECRET", "bank-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user, plan, order = _setup_order(db_session, amount_cents=199000)
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/bank",
        json={
            "gateway_transaction_id": "GW-2", "amount_cents": 150000,
            "content": f"chuyen tien {order.unique_code}", "received_at": datetime.datetime.utcnow().isoformat(),
        },
        headers={"x-webhook-secret": "bank-secret"},
    )

    assert response.status_code == 200
    txn = db_session.query(BankTransaction).filter_by(gateway_transaction_id="GW-2").one()
    assert txn.status == "unmatched"
    assert db_session.query(Order).filter_by(id=order.id).one().status == "pending"
    app.dependency_overrides.clear()


def test_unparseable_content_leaves_transaction_unmatched(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("BANK_WEBHOOK_SECRET", "bank-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/bank",
        json={
            "gateway_transaction_id": "GW-3", "amount_cents": 50000,
            "content": "no order code here", "received_at": datetime.datetime.utcnow().isoformat(),
        },
        headers={"x-webhook-secret": "bank-secret"},
    )

    assert response.status_code == 200
    txn = db_session.query(BankTransaction).filter_by(gateway_transaction_id="GW-3").one()
    assert txn.status == "unmatched"
    app.dependency_overrides.clear()


def test_duplicate_gateway_transaction_id_is_idempotent(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("BANK_WEBHOOK_SECRET", "bank-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user, plan, order = _setup_order(db_session, unique_code="OID-DUP")
    client = TestClient(app)
    payload = {
        "gateway_transaction_id": "GW-DUP", "amount_cents": 199000,
        "content": f"chuyen tien {order.unique_code}", "received_at": datetime.datetime.utcnow().isoformat(),
    }

    first = client.post("/billing/webhooks/bank", json=payload, headers={"x-webhook-secret": "bank-secret"})
    second = client.post("/billing/webhooks/bank", json=payload, headers={"x-webhook-secret": "bank-secret"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert db_session.query(BankTransaction).filter_by(gateway_transaction_id="GW-DUP").count() == 1
    app.dependency_overrides.clear()


def test_invalid_webhook_secret_rejected(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("BANK_WEBHOOK_SECRET", "bank-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/bank",
        json={
            "gateway_transaction_id": "GW-4", "amount_cents": 1000,
            "content": "x", "received_at": datetime.datetime.utcnow().isoformat(),
        },
        headers={"x-webhook-secret": "wrong-secret"},
    )

    assert response.status_code == 401
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_bank_webhook.py -v`
Expected: FAIL with `404 Not Found`

- [ ] **Step 3: Implement**

Add to `saas/billing/service.py` (near the top, after imports):

```python
import os
import re


def get_bank_webhook_secret() -> str:
    secret = os.environ.get("BANK_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("BANK_WEBHOOK_SECRET environment variable is not set")
    return secret


def extract_order_code(content: str) -> str | None:
    match = re.search(r"OID-[A-Z0-9]+", content)
    return match.group(0) if match else None
```

Add a Pydantic schema to `saas/schemas.py`:

```python
class BankWebhookPayload(BaseModel):
    gateway_transaction_id: str
    amount_cents: int
    content: str
    received_at: datetime.datetime
```

Append to `saas/routers/billing.py`:

```python
from ..billing.service import extract_order_code, get_bank_webhook_secret
from ..models import BankTransaction
from ..schemas import BankWebhookPayload


@router.post("/webhooks/bank")
def bank_webhook(
    payload: BankWebhookPayload,
    x_webhook_secret: str = Header(...),
    db: Session = Depends(get_db),
) -> dict:
    if x_webhook_secret != get_bank_webhook_secret():
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    existing = db.query(BankTransaction).filter_by(gateway_transaction_id=payload.gateway_transaction_id).one_or_none()
    if existing is not None:
        return {"received": True, "duplicate": True}

    order_code = extract_order_code(payload.content)
    matched_order = None
    if order_code is not None:
        candidate = db.query(Order).filter_by(unique_code=order_code, status="pending").one_or_none()
        if candidate is not None and candidate.amount_cents == payload.amount_cents:
            matched_order = candidate

    txn = BankTransaction(
        gateway_transaction_id=payload.gateway_transaction_id,
        amount_cents=payload.amount_cents,
        content=payload.content,
        received_at=payload.received_at,
        status="matched" if matched_order else "unmatched",
        matched_order_id=matched_order.id if matched_order else None,
    )
    db.add(txn)
    db.commit()

    if matched_order is not None:
        activate_subscription(db, matched_order)

    return {"received": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_bank_webhook.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/service.py saas/routers/billing.py saas/schemas.py tests/saas/test_billing_bank_webhook.py
git commit -m "feat(billing): add bank-transaction reconciliation webhook"
```

---

### Task 8: Plan-limit enforcement on episode creation

**Files:**
- Modify: `saas/routers/episodes.py`
- Create: `saas/billing/limits.py`
- Test: `tests/saas/test_plan_limits.py`

**Interfaces:**
- Consumes: `Subscription`, `Plan`, `Episode` (existing/Task 1).
- Produces: `check_episode_limit(db: Session, user: User) -> None` (raises `PlanLimitError` if the user's active subscription's `limits["episodes_per_month"]` is exceeded by episodes created in the last 30 days; users with no subscription row are treated as unlimited — that's the pre-billing default and matches `saas-foundation` behavior).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_plan_limits.py
import datetime

from saas.billing.limits import PlanLimitError, check_episode_limit
from saas.models import Episode, Plan, Subscription, User


def test_no_subscription_means_unlimited(db_session):
    user = User(email="nolimit@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()

    check_episode_limit(db_session, user)  # should not raise


def test_under_limit_allows_creation(db_session):
    user = User(email="under@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 5})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.add(Episode(user_id=user.id, title="ep1"))
    db_session.commit()

    check_episode_limit(db_session, user)  # 1 < 5, should not raise


def test_at_limit_rejects_creation(db_session):
    user = User(email="atlimit@x.com", password_hash="h")
    plan = Plan(name="Starter", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 1})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.add(Episode(user_id=user.id, title="ep1"))
    db_session.commit()

    try:
        check_episode_limit(db_session, user)
        assert False, "expected PlanLimitError"
    except PlanLimitError as e:
        assert e.code == "ERR_PLAN_LIMIT_REACHED"


def test_old_episodes_outside_window_dont_count(db_session):
    user = User(email="old@x.com", password_hash="h")
    plan = Plan(name="Starter", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 1})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    old_episode = Episode(
        user_id=user.id, title="ep_old",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=40),
    )
    db_session.add(old_episode)
    db_session.commit()

    check_episode_limit(db_session, user)  # outside 30-day window, should not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_plan_limits.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.billing.limits'`

- [ ] **Step 3: Implement**

```python
# saas/billing/limits.py
"""Plan-limit enforcement, checked before creating a new episode."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from ..models import Episode, Plan, Subscription, User


class PlanLimitError(Exception):
    def __init__(self, code: str = "ERR_PLAN_LIMIT_REACHED"):
        super().__init__(code)
        self.code = code


def check_episode_limit(db: Session, user: User) -> None:
    subscription = db.query(Subscription).filter_by(user_id=user.id).one_or_none()
    if subscription is None:
        return

    plan = db.query(Plan).filter_by(id=subscription.plan_id).one_or_none()
    if plan is None:
        return

    limit = plan.limits.get("episodes_per_month")
    if limit is None:
        return

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    count = (
        db.query(Episode)
        .filter(Episode.user_id == user.id, Episode.created_at >= cutoff)
        .count()
    )
    if count >= limit:
        raise PlanLimitError()
```

Modify `saas/routers/episodes.py` — add the import and the check at the top of `create_episode`:

```python
from ..billing.limits import PlanLimitError, check_episode_limit
```

```python
@router.post("", response_model=EpisodeOut, status_code=201)
def create_episode(
    payload: EpisodeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Episode:
    try:
        check_episode_limit(db, current_user)
    except PlanLimitError as e:
        raise HTTPException(status_code=403, detail=e.code)

    episode = Episode(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        tags=payload.tags,
        status="draft",
    )
    for index, scene_in in enumerate(payload.scenes):
        episode.scenes.append(Scene(order_index=index, narration_text=scene_in.narration_text))

    db.add(episode)
    db.commit()
    return episode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_plan_limits.py -v`
Expected: PASS (4 tests)

Also run the full existing episodes suite to confirm no regression:

Run: `py -m pytest tests/saas/test_episodes_routes.py -v`
Expected: PASS (all previously-passing tests still pass)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/limits.py saas/routers/episodes.py tests/saas/test_plan_limits.py
git commit -m "feat(billing): enforce plan episode limits on episode creation"
```

---

### Task 9: Subscription read endpoint + trial bookkeeping

**Files:**
- Modify: `saas/routers/billing.py`
- Modify: `saas/routers/auth.py`
- Test: `tests/saas/test_billing_subscription_route.py`, `tests/saas/test_billing_trial.py`

**Interfaces:**
- Consumes: `Subscription`, `SubscriptionOut` (Tasks 1/4); `Plan`.
- Produces: `GET /billing/subscription` (returns the current user's subscription, 404 if none); `start_trial(db: Session, user: User, plan: Plan) -> Subscription` in `saas/billing/service.py` (sets `status="trialing"`, `current_period_end = now + plan.trial_days`, `user.has_used_trial = True`; raises `VoucherError`-style `TrialError("ERR_TRIAL_ALREADY_USED")` if `user.has_used_trial` is already `True`).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_billing_subscription_route.py
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import Plan, Subscription, User
from saas.security import create_access_token


def test_get_subscription_returns_current_plan(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user = User(email="sub@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.get("/billing/subscription", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["plan_id"] == plan.id
    assert response.json()["status"] == "active"
    app.dependency_overrides.clear()


def test_get_subscription_404_when_none(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user = User(email="nosub@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.get("/billing/subscription", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    app.dependency_overrides.clear()
```

```python
# tests/saas/test_billing_trial.py
import pytest

from saas.billing.service import TrialError, start_trial
from saas.models import Plan, Subscription, User


def test_start_trial_creates_trialing_subscription(db_session):
    user = User(email="trial@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=7, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    sub = start_trial(db_session, user, plan)

    assert sub.status == "trialing"
    assert sub.current_period_end is not None
    assert db_session.query(User).filter_by(id=user.id).one().has_used_trial is True


def test_start_trial_rejects_repeat_trial(db_session):
    user = User(email="trial2@x.com", password_hash="h", has_used_trial=True)
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=7, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    with pytest.raises(TrialError) as exc_info:
        start_trial(db_session, user, plan)
    assert exc_info.value.code == "ERR_TRIAL_ALREADY_USED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_subscription_route.py tests/saas/test_billing_trial.py -v`
Expected: FAIL — `404 Not Found` for the route test, `ImportError` for the trial test

- [ ] **Step 3: Implement**

Add to `saas/billing/service.py`:

```python
class TrialError(Exception):
    def __init__(self, code: str = "ERR_TRIAL_ALREADY_USED"):
        super().__init__(code)
        self.code = code


def start_trial(db: Session, user: "User", plan: Plan) -> Subscription:
    if user.has_used_trial:
        raise TrialError()

    subscription = Subscription(
        user_id=user.id, plan_id=plan.id, status="trialing",
        current_period_end=datetime.datetime.utcnow() + datetime.timedelta(days=plan.trial_days),
    )
    user.has_used_trial = True
    db.add(subscription)
    db.commit()
    return subscription
```

Add the `User` import to `saas/billing/service.py`'s import line: `from ..models import Order, Plan, Subscription, User, Voucher`.

Append to `saas/routers/billing.py`:

```python
from ..schemas import SubscriptionOut


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Subscription:
    subscription = db.query(Subscription).filter_by(user_id=current_user.id).one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription")
    return subscription
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_subscription_route.py tests/saas/test_billing_trial.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/service.py saas/routers/billing.py tests/saas/test_billing_subscription_route.py tests/saas/test_billing_trial.py
git commit -m "feat(billing): add subscription read endpoint and trial start logic"
```

---

### Task 10: Env/setup docs + full-suite verification

**Files:**
- Modify: `.env.example`
- Modify: `SETUP.md`
- No new test file — this task verifies the whole branch.

- [ ] **Step 1: Add billing env vars**

Append to `.env.example` (below the existing `REDIS_URL` line):

```
STRIPE_SECRET_KEY=sk_test_changeme
STRIPE_WEBHOOK_SECRET=whsec_changeme
BANK_WEBHOOK_SECRET=change-me-to-a-long-random-string
```

- [ ] **Step 2: Document setup**

Append to `SETUP.md` a new section:

```markdown
## 6. Billing (Stripe + VN bank transfer)

1. Create a [Stripe](https://dashboard.stripe.com/test/apikeys) test-mode account, copy the **Secret key** into `STRIPE_SECRET_KEY`.
2. Create a webhook endpoint (Stripe CLI for local dev: `stripe listen --forward-to localhost:8000/billing/webhooks/stripe`), copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
3. Set `BANK_WEBHOOK_SECRET` to a long random string; configure your bank-transfer gateway (SePay/Casso) to send that value in the `x-webhook-secret` header when calling `POST /billing/webhooks/bank`.
4. Plans (`plans` table) are currently seeded manually via SQL/DB shell — the admin "create plan" UI that auto-syncs Stripe Products/Prices is a separate, not-yet-built plan.
```

- [ ] **Step 3: Run the full test suite**

Run: `py -m pytest -q`
Expected: all tests pass (existing 113 + this plan's new tests)

- [ ] **Step 4: Commit**

```bash
git add .env.example SETUP.md
git commit -m "docs(billing): document Stripe and bank-webhook setup"
```
