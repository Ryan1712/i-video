# Admin Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the admin-only surface from the SaaS spec — plan management (with Stripe Product/Price sync), voucher CRUD, manual bank-transaction review, user management (suspend/unsuspend), support-widget settings, and an append-only audit log with a searchable/CSV-exportable viewer — on top of the `saas` backend already on `master` (auth, episodes, billing).

**Architecture:** A single `require_admin` FastAPI dependency (built on the existing `get_current_user`) gates every route in this plan. A new `saas/audit.py` module exposes one function, `log_action`, that every admin-mutating route calls — this is the only way rows enter `audit_logs`, matching the spec's "unconditionally, not behind a feature flag" requirement. Stripe Product/Price sync extends the existing `saas/billing/stripe_client.py` wrapper rather than introducing a second Stripe touchpoint.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, `stripe` Python SDK (already a dependency), Pydantic v2, Python's stdlib `csv` module for export.

## Global Constraints

- Every sensitive action — plan changes, voucher CRUD, manual transaction approval, role/suspension changes, admin logins — is written to `audit_logs` unconditionally (spec, Admin capabilities section). No feature flag may gate this.
- `audit_logs` is append-only: no UPDATE or DELETE of an audit row anywhere in application code.
- Changing a plan's price creates a *new* Stripe Price; an existing Stripe Price is never mutated (spec, Admin capabilities bullet 1) — existing subscribers keep their original price.
- Reuse `saas/db.py` (`Base`, `get_db`), `saas/deps.py` (`get_current_user`), and the existing `tests/saas/conftest.py` fixtures (`db_session_factory`, `db_session`). Do not create a second DB setup or test-fixture file.
- Do **not** create `tests/saas/__init__.py` — it shadows the real `saas` package under pytest's import mode (bit a previous task; the fix was deleting it).
- Stripe calls are mocked in tests — no real network calls in the suite.
- All admin routes require `role == "admin"`; a non-admin caller gets 403, not 404 (403 is correct here — admin routes are app-wide, not per-resource-ownership where 404 prevents existence leaks).

---

## File Structure

- Create: `saas/audit.py` — `log_action(db, actor, action, target_type, target_id, before=None, after=None) -> AuditLog`.
- Create: `saas/admin_deps.py` — `require_admin(current_user: User = Depends(get_current_user)) -> User`.
- Create: `saas/routers/admin_plans.py` — plan CRUD + Stripe sync.
- Create: `saas/routers/admin_vouchers.py` — voucher CRUD.
- Create: `saas/routers/admin_transactions.py` — manual bank-transaction review.
- Create: `saas/routers/admin_users.py` — user list/suspend/unsuspend.
- Create: `saas/routers/admin_settings.py` — `site_settings` read/write (support widgets).
- Create: `saas/routers/admin_audit.py` — audit log search/filter + CSV export.
- Modify: `saas/models.py` — add `AuditLog`, `SiteSetting`; add `User.is_suspended`.
- Modify: `saas/schemas.py` — add admin request/response models.
- Modify: `saas/main.py` — register the six new routers.
- Modify: `saas/billing/stripe_client.py` — add `create_product`, `create_price`.
- Modify: `saas/deps.py` — `get_current_user` rejects suspended users.
- Modify: `saas/routers/auth.py` — log admin logins via `log_action`.
- Test: `tests/saas/test_audit.py`, `tests/saas/test_admin_deps.py`, `tests/saas/test_admin_plans.py`, `tests/saas/test_admin_vouchers.py`, `tests/saas/test_admin_transactions.py`, `tests/saas/test_admin_users.py`, `tests/saas/test_admin_settings.py`, `tests/saas/test_admin_audit.py`.

---

### Task 1: Audit log model + `log_action` + `require_admin`

**Files:**
- Modify: `saas/models.py`
- Create: `saas/audit.py`
- Create: `saas/admin_deps.py`
- Test: `tests/saas/test_audit.py`, `tests/saas/test_admin_deps.py`

**Interfaces:**
- Produces: `AuditLog(id, actor_user_id, actor_role, action, target_type, target_id, before_data, after_data, ip_address, created_at)`. `log_action(db: Session, actor: User, action: str, target_type: str, target_id: int, before: dict | None = None, after: dict | None = None, ip_address: str | None = None) -> AuditLog`. `require_admin(current_user: User = Depends(get_current_user)) -> User` (raises `HTTPException(403)` if `current_user.role != "admin"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_audit.py
from saas.audit import log_action
from saas.models import AuditLog, User


def test_log_action_writes_audit_row(db_session):
    admin = User(email="admin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()

    entry = log_action(
        db_session, actor=admin, action="plan.create", target_type="plan", target_id=7,
        before=None, after={"name": "Pro", "price_cents": 199000},
    )

    assert entry.id is not None
    fetched = db_session.query(AuditLog).one()
    assert fetched.actor_user_id == admin.id
    assert fetched.actor_role == "admin"
    assert fetched.action == "plan.create"
    assert fetched.target_type == "plan"
    assert fetched.target_id == 7
    assert fetched.before_data is None
    assert fetched.after_data == {"name": "Pro", "price_cents": 199000}


def test_log_action_records_ip_address(db_session):
    admin = User(email="admin2@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()

    entry = log_action(
        db_session, actor=admin, action="admin.login", target_type="user", target_id=admin.id,
        ip_address="127.0.0.1",
    )

    assert entry.ip_address == "127.0.0.1"
```

```python
# tests/saas/test_admin_deps.py
import pytest
from fastapi import HTTPException

from saas.admin_deps import require_admin
from saas.models import User


def test_require_admin_allows_admin():
    admin = User(email="a@x.com", password_hash="h", role="admin")
    assert require_admin(admin) is admin


def test_require_admin_rejects_non_admin():
    user = User(email="u@x.com", password_hash="h", role="user")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(user)
    assert exc_info.value.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_audit.py tests/saas/test_admin_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.audit'`

- [ ] **Step 3: Implement**

Append to `saas/models.py`:

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
```

Also add `is_suspended` to `User`, right after `has_used_trial`:

```python
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

```python
# saas/audit.py
"""The single entry point for writing audit_logs rows — append-only, called by every admin-mutating route."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog, User


def log_action(
    db: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: int,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor.id,
        actor_role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_data=before,
        after_data=after,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry
```

```python
# saas/admin_deps.py
"""Admin-only route guard, built on top of the existing get_current_user dependency."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from .deps import get_current_user
from .models import User


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_audit.py tests/saas/test_admin_deps.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/models.py saas/audit.py saas/admin_deps.py tests/saas/test_audit.py tests/saas/test_admin_deps.py
git commit -m "feat(admin): add audit_logs model, log_action, and require_admin dependency"
```

---

### Task 2: Suspended-user login block + admin-login auditing

**Files:**
- Modify: `saas/deps.py`
- Modify: `saas/routers/auth.py`
- Test: `tests/saas/test_deps.py` (extend), `tests/saas/test_auth_routes.py` (extend)

**Interfaces:**
- Consumes: `User.is_suspended` (Task 1), `log_action` (Task 1).
- Produces: `get_current_user` now raises `HTTPException(403, "Account suspended")` for suspended users; `POST /auth/login` calls `log_action(db, actor=user, action="admin.login", ...)` when `user.role == "admin"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/saas/test_deps.py`:

```python
def test_get_current_user_rejects_suspended_user(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    from saas.models import User
    from saas.security import create_access_token

    user = User(email="suspended@x.com", password_hash="h", is_suspended=True)
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")

    from fastapi import HTTPException

    from saas.deps import get_current_user

    try:
        get_current_user(authorization=f"Bearer {token}", db=db_session)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 403
```

Add to `tests/saas/test_auth_routes.py`:

```python
def test_admin_login_is_audited(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    from fastapi.testclient import TestClient

    from saas.audit import log_action  # noqa: F401  (imported for readability of intent)
    from saas.db import get_db
    from saas.main import app
    from saas.models import AuditLog, User
    from saas.security import hash_password

    app.dependency_overrides[get_db] = lambda: db_session
    admin = User(email="adminlogin@x.com", password_hash=hash_password("pw"), role="admin")
    db_session.add(admin)
    db_session.commit()
    client = TestClient(app)

    response = client.post("/auth/login", json={"email": "adminlogin@x.com", "password": "pw"})

    assert response.status_code == 200
    entry = db_session.query(AuditLog).filter_by(action="admin.login").one()
    assert entry.actor_user_id == admin.id
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_deps.py::test_get_current_user_rejects_suspended_user tests/saas/test_auth_routes.py::test_admin_login_is_audited -v`
Expected: FAIL — suspended test fails because no suspension check exists yet (login succeeds); audit test fails because no `AuditLog` row is written.

- [ ] **Step 3: Implement**

Modify `saas/deps.py` — add the check after fetching `user`, before `return user`:

```python
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")

    return user
```

Read `saas/routers/auth.py` first to see the exact `login` function body, then add the audit call right before its `return` statement (after the token is created, using the already-loaded `user` and `db`):

```python
    if user.role == "admin":
        log_action(db, actor=user, action="admin.login", target_type="user", target_id=user.id)
```

Add `from ..audit import log_action` to the top of `saas/routers/auth.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_deps.py tests/saas/test_auth_routes.py -v`
Expected: PASS (all tests, including the two new ones)

- [ ] **Step 5: Commit**

```bash
git add saas/deps.py saas/routers/auth.py tests/saas/test_deps.py tests/saas/test_auth_routes.py
git commit -m "feat(admin): block suspended-user logins and audit admin logins"
```

---

### Task 3: Stripe Product/Price sync helpers

**Files:**
- Modify: `saas/billing/stripe_client.py`
- Test: `tests/saas/test_billing_stripe_client.py` (extend)

**Interfaces:**
- Produces: `create_product(name: str) -> stripe.Product`, `create_price(product_id: str, price_cents: int, currency: str, billing_interval: str) -> stripe.Price` (both call the real Stripe SDK, mocked in tests, following the existing wrapper pattern in this file).

- [ ] **Step 1: Write the failing test**

Add to `tests/saas/test_billing_stripe_client.py`:

```python
@patch("saas.billing.stripe_client.stripe.Product.create")
def test_create_product_calls_stripe_sdk(mock_create, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    mock_create.return_value = MagicMock(id="prod_123")

    from saas.billing.stripe_client import create_product

    product = create_product("Pro Plan")

    assert product.id == "prod_123"
    mock_create.assert_called_once_with(name="Pro Plan")


@patch("saas.billing.stripe_client.stripe.Price.create")
def test_create_price_calls_stripe_sdk(mock_create, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    mock_create.return_value = MagicMock(id="price_123")

    from saas.billing.stripe_client import create_price

    price = create_price("prod_123", 199000, "vnd", "month")

    assert price.id == "price_123"
    mock_create.assert_called_once_with(
        product="prod_123", unit_amount=199000, currency="vnd",
        recurring={"interval": "month"},
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_billing_stripe_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_product'`

- [ ] **Step 3: Implement**

Append to `saas/billing/stripe_client.py`:

```python
def create_product(name: str) -> stripe.Product:
    stripe.api_key = get_stripe_secret_key()
    return stripe.Product.create(name=name)


def create_price(product_id: str, price_cents: int, currency: str, billing_interval: str) -> stripe.Price:
    stripe.api_key = get_stripe_secret_key()
    return stripe.Price.create(
        product=product_id, unit_amount=price_cents, currency=currency.lower(),
        recurring={"interval": billing_interval},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_billing_stripe_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/billing/stripe_client.py tests/saas/test_billing_stripe_client.py
git commit -m "feat(admin): add Stripe Product/Price sync helpers"
```

---

### Task 4: Admin plan management (CRUD + Stripe sync + audit)

**Files:**
- Create: `saas/routers/admin_plans.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_plans.py`

**Interfaces:**
- Consumes: `require_admin` (Task 1), `log_action` (Task 1), `create_product`, `create_price` (Task 3), `Plan` model.
- Produces: `router` (prefix `/admin/plans`) with `POST /admin/plans`, `GET /admin/plans`, `PATCH /admin/plans/{plan_id}`. `PlanIn(name, price_cents, currency, billing_interval, trial_days, limits)`, `PlanOut(id, name, price_cents, currency, billing_interval, stripe_price_id, trial_days, limits)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_plans.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, Plan, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="planadmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


@patch("saas.routers.admin_plans.create_price")
@patch("saas.routers.admin_plans.create_product")
def test_create_plan_syncs_to_stripe_and_audits(mock_create_product, mock_create_price, db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    mock_create_product.return_value = MagicMock(id="prod_abc")
    mock_create_price.return_value = MagicMock(id="price_abc")
    client = TestClient(app)

    response = client.post(
        "/admin/plans",
        json={"name": "Pro", "price_cents": 199000, "currency": "VND", "billing_interval": "month", "trial_days": 7, "limits": {"episodes_per_month": 10}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["stripe_price_id"] == "price_abc"
    plan = db_session.query(Plan).filter_by(id=body["id"]).one()
    assert plan.stripe_price_id == "price_abc"
    entry = db_session.query(AuditLog).filter_by(action="plan.create").one()
    assert entry.after_data["name"] == "Pro"
    app.dependency_overrides.clear()


def test_create_plan_rejects_non_admin(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    user = User(email="regular@x.com", password_hash="h", role="user")
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.id, "test-secret-test-secret")
    client = TestClient(app)

    response = client.post(
        "/admin/plans",
        json={"name": "Pro", "price_cents": 1, "currency": "VND", "billing_interval": "month", "trial_days": 0, "limits": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_list_plans(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    db_session.add(Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", trial_days=0, limits={}))
    db_session.commit()
    client = TestClient(app)

    response = client.get("/admin/plans", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    app.dependency_overrides.clear()


@patch("saas.routers.admin_plans.create_price")
def test_update_plan_price_creates_new_stripe_price(mock_create_price, db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", stripe_price_id="price_old", trial_days=7, limits={})
    db_session.add(plan)
    db_session.commit()
    mock_create_price.return_value = MagicMock(id="price_new")
    client = TestClient(app)

    response = client.patch(
        f"/admin/plans/{plan.id}",
        json={"name": "Pro", "price_cents": 249000, "currency": "VND", "billing_interval": "month", "trial_days": 7, "limits": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["stripe_price_id"] == "price_new"
    mock_create_price.assert_called_once()
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_plans.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.admin_plans'`

- [ ] **Step 3: Implement**

Add to `saas/schemas.py`:

```python
class PlanIn(BaseModel):
    name: str
    price_cents: int
    currency: str = "VND"
    billing_interval: str = "month"
    trial_days: int = 0
    limits: dict = {}


class PlanOut(BaseModel):
    id: int
    name: str
    price_cents: int
    currency: str
    billing_interval: str
    stripe_price_id: str | None
    trial_days: int
    limits: dict

    class Config:
        from_attributes = True
```

```python
# saas/routers/admin_plans.py
"""Admin plan management: CRUD with automatic Stripe Product/Price sync."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..billing.stripe_client import create_price, create_product
from ..db import get_db
from ..models import Plan, User
from ..schemas import PlanIn, PlanOut

router = APIRouter(prefix="/admin/plans", tags=["admin"])


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(
    payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Plan:
    product = create_product(payload.name)
    price = create_price(product.id, payload.price_cents, payload.currency, payload.billing_interval)

    plan = Plan(
        name=payload.name, price_cents=payload.price_cents, currency=payload.currency,
        billing_interval=payload.billing_interval, stripe_price_id=price.id,
        trial_days=payload.trial_days, limits=payload.limits,
    )
    db.add(plan)
    db.commit()

    log_action(
        db, actor=current_user, action="plan.create", target_type="plan", target_id=plan.id,
        after={"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id},
    )
    return plan


@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Plan]:
    return db.query(Plan).all()


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: int, payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Plan:
    plan = db.query(Plan).filter_by(id=plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    before = {"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id}

    price_changed = payload.price_cents != plan.price_cents or payload.billing_interval != plan.billing_interval
    if price_changed and plan.stripe_price_id is not None:
        new_price = create_price(plan.stripe_price_id.split("_")[0] or "prod_unknown", payload.price_cents, payload.currency, payload.billing_interval)
        plan.stripe_price_id = new_price.id

    plan.name = payload.name
    plan.price_cents = payload.price_cents
    plan.currency = payload.currency
    plan.billing_interval = payload.billing_interval
    plan.trial_days = payload.trial_days
    plan.limits = payload.limits
    db.commit()

    log_action(
        db, actor=current_user, action="plan.update", target_type="plan", target_id=plan.id,
        before=before, after={"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id},
    )
    return plan
```

Note: `update_plan`'s `create_price` call passes `plan.stripe_price_id.split("_")[0]` as a placeholder product id, which is wrong (a Price id isn't a Product id). Fix it properly: add a `stripe_product_id` column is out of scope for this task's interface (not listed above), so instead call Stripe to look up the existing Price's product first. Replace that line with:

```python
    if price_changed and plan.stripe_price_id is not None:
        import stripe

        from ..billing.stripe_client import get_stripe_secret_key

        stripe.api_key = get_stripe_secret_key()
        existing_price = stripe.Price.retrieve(plan.stripe_price_id)
        new_price = create_price(existing_price.product, payload.price_cents, payload.currency, payload.billing_interval)
        plan.stripe_price_id = new_price.id
```

This requires the test's `test_update_plan_price_creates_new_stripe_price` to also mock `stripe.Price.retrieve` — add this patch decorator to that test: `@patch("saas.routers.admin_plans.stripe.Price.retrieve")` with `mock_retrieve.return_value = MagicMock(product="prod_old")`, and add `mock_retrieve` as the outermost parameter (decorators apply bottom-up, so the retrieve patch must be the topmost decorator to appear last in the parameter list — order: `@patch(".create_price")` then `@patch("...stripe.Price.retrieve")` above it, parameters `(self, mock_retrieve, mock_create_price, ...)`). Add `import stripe` at the top of `saas/routers/admin_plans.py` (module-level, not just inside the function) so the test can patch `saas.routers.admin_plans.stripe.Price.retrieve`, and remove the function-local `import stripe` line.

Update `saas/main.py`:

```python
from .routers import admin_plans, auth, billing, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_plans.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/admin_plans.py saas/schemas.py saas/main.py tests/saas/test_admin_plans.py
git commit -m "feat(admin): add plan management with Stripe Product/Price sync"
```

---

### Task 5: Admin voucher CRUD

**Files:**
- Create: `saas/routers/admin_vouchers.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_vouchers.py`

**Interfaces:**
- Consumes: `require_admin`, `log_action` (Task 1), `Voucher` model.
- Produces: `router` (prefix `/admin/vouchers`) with `POST /admin/vouchers`, `GET /admin/vouchers`, `DELETE /admin/vouchers/{voucher_id}`. `VoucherIn(code, discount_type, discount_value, max_uses, expires_at, applicable_plan_ids)`, `VoucherOut(id, code, discount_type, discount_value, max_uses, used_count, expires_at, applicable_plan_ids)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_vouchers.py
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, Plan, User, Voucher
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="voucheradmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def test_create_voucher_and_audit(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add(plan)
    db_session.commit()
    client = TestClient(app)

    response = client.post(
        "/admin/vouchers",
        json={"code": "SALE10", "discount_type": "percent", "discount_value": 10, "max_uses": 100, "applicable_plan_ids": [plan.id]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert db_session.query(Voucher).filter_by(code="SALE10").one() is not None
    assert db_session.query(AuditLog).filter_by(action="voucher.create").one() is not None
    app.dependency_overrides.clear()


def test_list_vouchers(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    db_session.add(Voucher(code="X", discount_type="fixed", discount_value=1000, applicable_plan_ids=[]))
    db_session.commit()
    client = TestClient(app)

    response = client.get("/admin/vouchers", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    app.dependency_overrides.clear()


def test_delete_voucher_and_audit(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    voucher = Voucher(code="DEL", discount_type="fixed", discount_value=1000, applicable_plan_ids=[])
    db_session.add(voucher)
    db_session.commit()
    client = TestClient(app)

    response = client.delete(f"/admin/vouchers/{voucher.id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert db_session.query(Voucher).filter_by(id=voucher.id).one_or_none() is None
    assert db_session.query(AuditLog).filter_by(action="voucher.delete").one() is not None
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_vouchers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.admin_vouchers'`

- [ ] **Step 3: Implement**

Add to `saas/schemas.py`:

```python
class VoucherIn(BaseModel):
    code: str
    discount_type: str
    discount_value: int
    max_uses: int = 1
    expires_at: datetime.datetime | None = None
    applicable_plan_ids: list[int] = []


class VoucherOut(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: int
    max_uses: int
    used_count: int
    expires_at: datetime.datetime | None
    applicable_plan_ids: list[int]

    class Config:
        from_attributes = True
```

```python
# saas/routers/admin_vouchers.py
"""Admin voucher CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import User, Voucher
from ..schemas import VoucherIn, VoucherOut

router = APIRouter(prefix="/admin/vouchers", tags=["admin"])


@router.post("", response_model=VoucherOut, status_code=201)
def create_voucher(
    payload: VoucherIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Voucher:
    voucher = Voucher(
        code=payload.code, discount_type=payload.discount_type, discount_value=payload.discount_value,
        max_uses=payload.max_uses, expires_at=payload.expires_at, applicable_plan_ids=payload.applicable_plan_ids,
    )
    db.add(voucher)
    db.commit()

    log_action(
        db, actor=current_user, action="voucher.create", target_type="voucher", target_id=voucher.id,
        after={"code": voucher.code, "discount_type": voucher.discount_type, "discount_value": voucher.discount_value},
    )
    return voucher


@router.get("", response_model=list[VoucherOut])
def list_vouchers(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Voucher]:
    return db.query(Voucher).all()


@router.delete("/{voucher_id}", status_code=204)
def delete_voucher(
    voucher_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> None:
    voucher = db.query(Voucher).filter_by(id=voucher_id).one_or_none()
    if voucher is None:
        raise HTTPException(status_code=404, detail="Voucher not found")

    before = {"code": voucher.code, "discount_type": voucher.discount_type, "discount_value": voucher.discount_value}
    db.delete(voucher)
    db.commit()

    log_action(db, actor=current_user, action="voucher.delete", target_type="voucher", target_id=voucher_id, before=before)
```

Update `saas/main.py` to also register `admin_vouchers.router`:

```python
from .routers import admin_plans, admin_vouchers, auth, billing, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_vouchers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/admin_vouchers.py saas/schemas.py saas/main.py tests/saas/test_admin_vouchers.py
git commit -m "feat(admin): add voucher CRUD routes"
```

---

### Task 6: Manual bank-transaction review

**Files:**
- Create: `saas/routers/admin_transactions.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_transactions.py`

**Interfaces:**
- Consumes: `require_admin`, `log_action` (Task 1), `activate_subscription` (existing `saas/billing/service.py`), `BankTransaction`, `Order` models.
- Produces: `router` (prefix `/admin/transactions`) with `GET /admin/transactions/unmatched`, `POST /admin/transactions/{transaction_id}/link/{order_id}`. `BankTransactionOut(id, gateway_transaction_id, amount_cents, content, received_at, status, matched_order_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_transactions.py
import datetime

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, BankTransaction, Order, Plan, Subscription, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="txnadmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def test_list_unmatched_transactions(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    db_session.add(BankTransaction(
        gateway_transaction_id="GW-X", amount_cents=1000, content="??",
        received_at=datetime.datetime.utcnow(), status="unmatched",
    ))
    db_session.add(BankTransaction(
        gateway_transaction_id="GW-Y", amount_cents=2000, content="matched one",
        received_at=datetime.datetime.utcnow(), status="matched",
    ))
    db_session.commit()
    client = TestClient(app)

    response = client.get("/admin/transactions/unmatched", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["gateway_transaction_id"] == "GW-X"
    app.dependency_overrides.clear()


def test_manually_link_transaction_activates_subscription_and_audits(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    user = User(email="payer@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=99000, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=99000, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-MANUAL",
    )
    txn = BankTransaction(
        gateway_transaction_id="GW-MANUAL", amount_cents=95000, content="off by a bit",
        received_at=datetime.datetime.utcnow(), status="unmatched",
    )
    db_session.add_all([order, txn])
    db_session.commit()
    client = TestClient(app)

    response = client.post(
        f"/admin/transactions/{txn.id}/link/{order.id}", headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    refreshed_order = db_session.query(Order).filter_by(id=order.id).one()
    assert refreshed_order.status == "paid"
    refreshed_txn = db_session.query(BankTransaction).filter_by(id=txn.id).one()
    assert refreshed_txn.status == "matched"
    assert refreshed_txn.matched_order_id == order.id
    assert db_session.query(Subscription).filter_by(user_id=user.id).one().status == "active"
    entry = db_session.query(AuditLog).filter_by(action="transaction.manual_link").one()
    assert entry.target_id == txn.id
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_transactions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.admin_transactions'`

- [ ] **Step 3: Implement**

Add to `saas/schemas.py`:

```python
class BankTransactionOut(BaseModel):
    id: int
    gateway_transaction_id: str
    amount_cents: int
    content: str
    received_at: datetime.datetime
    status: str
    matched_order_id: int | None

    class Config:
        from_attributes = True
```

```python
# saas/routers/admin_transactions.py
"""Admin manual review/linking of unmatched bank transactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..billing.service import activate_subscription
from ..db import get_db
from ..models import BankTransaction, Order, User
from ..schemas import BankTransactionOut

router = APIRouter(prefix="/admin/transactions", tags=["admin"])


@router.get("/unmatched", response_model=list[BankTransactionOut])
def list_unmatched(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[BankTransaction]:
    return db.query(BankTransaction).filter_by(status="unmatched").all()


@router.post("/{transaction_id}/link/{order_id}", response_model=BankTransactionOut)
def link_transaction(
    transaction_id: int, order_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> BankTransaction:
    txn = db.query(BankTransaction).filter_by(id=transaction_id).one_or_none()
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    order = db.query(Order).filter_by(id=order_id).one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    txn.status = "matched"
    txn.matched_order_id = order.id
    db.commit()
    activate_subscription(db, order)

    log_action(
        db, actor=current_user, action="transaction.manual_link", target_type="bank_transaction",
        target_id=txn.id, after={"matched_order_id": order.id},
    )
    return txn
```

Update `saas/main.py` to also register `admin_transactions.router`:

```python
from .routers import admin_plans, admin_transactions, admin_vouchers, auth, billing, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_transactions.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/admin_transactions.py saas/schemas.py saas/main.py tests/saas/test_admin_transactions.py
git commit -m "feat(admin): add manual bank-transaction review and linking"
```

---

### Task 7: User management (list/suspend/unsuspend)

**Files:**
- Create: `saas/routers/admin_users.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_users.py`

**Interfaces:**
- Consumes: `require_admin`, `log_action` (Task 1), `User.is_suspended` (Task 1), `Subscription`, `Plan` models.
- Produces: `router` (prefix `/admin/users`) with `GET /admin/users`, `POST /admin/users/{user_id}/suspend`, `POST /admin/users/{user_id}/unsuspend`. `UserOut(id, email, role, is_suspended, plan_name)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_users.py
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, Plan, Subscription, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="useradmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def test_list_users_includes_plan_name(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    user = User(email="plain@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.commit()
    client = TestClient(app)

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = {row["email"]: row for row in response.json()}
    assert body["plain@x.com"]["plan_name"] == "Pro"
    assert body["plain@x.com"]["is_suspended"] is False
    app.dependency_overrides.clear()


def test_suspend_and_unsuspend_user_audits_both(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    user = User(email="tosuspend@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    client = TestClient(app)

    suspend_response = client.post(f"/admin/users/{user.id}/suspend", headers={"Authorization": f"Bearer {token}"})
    assert suspend_response.status_code == 200
    assert db_session.query(User).filter_by(id=user.id).one().is_suspended is True

    unsuspend_response = client.post(f"/admin/users/{user.id}/unsuspend", headers={"Authorization": f"Bearer {token}"})
    assert unsuspend_response.status_code == 200
    assert db_session.query(User).filter_by(id=user.id).one().is_suspended is False

    actions = {row.action for row in db_session.query(AuditLog).filter_by(target_id=user.id).all()}
    assert actions == {"user.suspend", "user.unsuspend"}
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_users.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.admin_users'`

- [ ] **Step 3: Implement**

Add to `saas/schemas.py`:

```python
class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_suspended: bool
    plan_name: str | None
```

```python
# saas/routers/admin_users.py
"""Admin user management: list with current plan, suspend/unsuspend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import Plan, Subscription, User
from ..schemas import UserOut

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[UserOut]:
    users = db.query(User).all()
    result = []
    for user in users:
        subscription = db.query(Subscription).filter_by(user_id=user.id).one_or_none()
        plan_name = None
        if subscription is not None:
            plan = db.query(Plan).filter_by(id=subscription.plan_id).one_or_none()
            plan_name = plan.name if plan is not None else None
        result.append(UserOut(id=user.id, email=user.email, role=user.role, is_suspended=user.is_suspended, plan_name=plan_name))
    return result


@router.post("/{user_id}/suspend", response_model=UserOut)
def suspend_user(
    user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> UserOut:
    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = True
    db.commit()
    log_action(db, actor=current_user, action="user.suspend", target_type="user", target_id=user.id)
    return UserOut(id=user.id, email=user.email, role=user.role, is_suspended=user.is_suspended, plan_name=None)


@router.post("/{user_id}/unsuspend", response_model=UserOut)
def unsuspend_user(
    user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> UserOut:
    user = db.query(User).filter_by(id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_suspended = False
    db.commit()
    log_action(db, actor=current_user, action="user.unsuspend", target_type="user", target_id=user.id)
    return UserOut(id=user.id, email=user.email, role=user.role, is_suspended=user.is_suspended, plan_name=None)
```

Update `saas/main.py` to also register `admin_users.router`:

```python
from .routers import admin_plans, admin_transactions, admin_users, admin_vouchers, auth, billing, episodes, jobs

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
app.include_router(admin_users.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_users.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/admin_users.py saas/schemas.py saas/main.py tests/saas/test_admin_users.py
git commit -m "feat(admin): add user list/suspend/unsuspend routes"
```

---

### Task 8: Support widget settings (`site_settings`)

**Files:**
- Modify: `saas/models.py`
- Create: `saas/routers/admin_settings.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_settings.py`

**Interfaces:**
- Produces: `SiteSetting(key, value)` (primary key `key`). `router` (prefix `/admin/settings`) with `GET /admin/settings`, `PUT /admin/settings/{key}`. `SiteSettingOut(key, value)`. Recognized keys per spec: `messenger_page_id`, `zalo_oa_id`, `facebook_page_url`, `messenger_enabled`, `zalo_enabled`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_settings.py
from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, SiteSetting, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="settingsadmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def test_list_settings_empty_by_default(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    client = TestClient(app)

    response = client.get("/admin/settings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []
    app.dependency_overrides.clear()


def test_set_setting_creates_and_audits(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    client = TestClient(app)

    response = client.put(
        "/admin/settings/messenger_page_id", json={"value": "1234567"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert db_session.query(SiteSetting).filter_by(key="messenger_page_id").one().value == "1234567"
    assert db_session.query(AuditLog).filter_by(action="setting.update").one() is not None
    app.dependency_overrides.clear()


def test_update_setting_overwrites_existing_value(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    db_session.add(SiteSetting(key="zalo_oa_id", value="old"))
    db_session.commit()
    client = TestClient(app)

    response = client.put(
        "/admin/settings/zalo_oa_id", json={"value": "new"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert db_session.query(SiteSetting).filter_by(key="zalo_oa_id").one().value == "new"
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_settings.py -v`
Expected: FAIL with `ImportError: cannot import name 'SiteSetting'`

- [ ] **Step 3: Implement**

Append to `saas/models.py`:

```python
class SiteSetting(Base):
    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
```

Add to `saas/schemas.py`:

```python
class SiteSettingIn(BaseModel):
    value: str


class SiteSettingOut(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True
```

```python
# saas/routers/admin_settings.py
"""Admin-configurable site_settings, used for support-widget IDs/toggles."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..db import get_db
from ..models import SiteSetting, User
from ..schemas import SiteSettingIn, SiteSettingOut

router = APIRouter(prefix="/admin/settings", tags=["admin"])


@router.get("", response_model=list[SiteSettingOut])
def list_settings(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[SiteSetting]:
    return db.query(SiteSetting).all()


@router.put("/{key}", response_model=SiteSettingOut)
def set_setting(
    key: str, payload: SiteSettingIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> SiteSetting:
    setting = db.query(SiteSetting).filter_by(key=key).one_or_none()
    before = {"value": setting.value} if setting is not None else None

    if setting is None:
        setting = SiteSetting(key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    db.commit()

    log_action(
        db, actor=current_user, action="setting.update", target_type="site_setting", target_id=0,
        before=before, after={"key": key, "value": payload.value},
    )
    return setting
```

Update `saas/main.py` to also register `admin_settings.router`:

```python
from .routers import (
    admin_plans,
    admin_settings,
    admin_transactions,
    admin_users,
    admin_vouchers,
    auth,
    billing,
    episodes,
    jobs,
)

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
app.include_router(admin_users.router)
app.include_router(admin_settings.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_settings.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/models.py saas/routers/admin_settings.py saas/schemas.py saas/main.py tests/saas/test_admin_settings.py
git commit -m "feat(admin): add site_settings support-widget configuration"
```

---

### Task 9: Audit log viewer (search/filter + CSV export)

**Files:**
- Create: `saas/routers/admin_audit.py`
- Modify: `saas/schemas.py`
- Modify: `saas/main.py`
- Test: `tests/saas/test_admin_audit.py`

**Interfaces:**
- Consumes: `require_admin` (Task 1), `AuditLog` model.
- Produces: `router` (prefix `/admin/audit`) with `GET /admin/audit` (query params `actor_user_id: int | None`, `action: str | None`, `from_date: datetime | None`, `to_date: datetime | None`) and `GET /admin/audit/export.csv` (same filters, returns `text/csv`). `AuditLogOut(id, actor_user_id, actor_role, action, target_type, target_id, before_data, after_data, ip_address, created_at)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/saas/test_admin_audit.py
import datetime

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
from saas.models import AuditLog, User
from saas.security import create_access_token


def _admin_token(db_session):
    admin = User(email="auditadmin@x.com", password_hash="h", role="admin")
    db_session.add(admin)
    db_session.commit()
    return admin, create_access_token(admin.id, "test-secret-test-secret")


def _seed_logs(db_session, admin_id):
    db_session.add_all([
        AuditLog(actor_user_id=admin_id, actor_role="admin", action="plan.create", target_type="plan", target_id=1, created_at=datetime.datetime(2026, 1, 1)),
        AuditLog(actor_user_id=admin_id, actor_role="admin", action="voucher.create", target_type="voucher", target_id=2, created_at=datetime.datetime(2026, 2, 1)),
    ])
    db_session.commit()


def test_filter_by_action(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    _seed_logs(db_session, admin.id)
    client = TestClient(app)

    response = client.get(
        "/admin/audit", params={"action": "plan.create"}, headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["action"] == "plan.create"
    app.dependency_overrides.clear()


def test_filter_by_date_range(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    _seed_logs(db_session, admin.id)
    client = TestClient(app)

    response = client.get(
        "/admin/audit", params={"from_date": "2026-01-15T00:00:00"}, headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["action"] == "voucher.create"
    app.dependency_overrides.clear()


def test_csv_export(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    _seed_logs(db_session, admin.id)
    client = TestClient(app)

    response = client.get("/admin/audit/export.csv", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "plan.create" in response.text
    assert "voucher.create" in response.text
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest tests/saas/test_admin_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'saas.routers.admin_audit'`

- [ ] **Step 3: Implement**

Add to `saas/schemas.py`:

```python
class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int
    actor_role: str
    action: str
    target_type: str
    target_id: int
    before_data: dict | None
    after_data: dict | None
    ip_address: str | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True
```

```python
# saas/routers/admin_audit.py
"""Audit log search/filter and CSV export, per spec: searchable by actor, action type, date range."""
from __future__ import annotations

import csv
import datetime
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..db import get_db
from ..models import AuditLog, User
from ..schemas import AuditLogOut

router = APIRouter(prefix="/admin/audit", tags=["admin"])


def _filtered_query(
    db: Session,
    actor_user_id: int | None,
    action: str | None,
    from_date: datetime.datetime | None,
    to_date: datetime.datetime | None,
):
    query = db.query(AuditLog)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if from_date is not None:
        query = query.filter(AuditLog.created_at >= from_date)
    if to_date is not None:
        query = query.filter(AuditLog.created_at <= to_date)
    return query.order_by(AuditLog.created_at.desc())


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    actor_user_id: int | None = None,
    action: str | None = None,
    from_date: datetime.datetime | None = None,
    to_date: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[AuditLog]:
    return _filtered_query(db, actor_user_id, action, from_date, to_date).all()


@router.get("/export.csv")
def export_audit_logs_csv(
    actor_user_id: int | None = None,
    action: str | None = None,
    from_date: datetime.datetime | None = None,
    to_date: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> StreamingResponse:
    rows = _filtered_query(db, actor_user_id, action, from_date, to_date).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "actor_user_id", "actor_role", "action", "target_type", "target_id", "created_at"])
    for row in rows:
        writer.writerow([row.id, row.actor_user_id, row.actor_role, row.action, row.target_type, row.target_id, row.created_at])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
```

Update `saas/main.py` to also register `admin_audit.router` (final version of the file):

```python
from .routers import (
    admin_audit,
    admin_plans,
    admin_settings,
    admin_transactions,
    admin_users,
    admin_vouchers,
    auth,
    billing,
    episodes,
    jobs,
)

app = FastAPI(title="What If API")
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(episodes.router)
app.include_router(jobs.router)
app.include_router(admin_plans.router)
app.include_router(admin_vouchers.router)
app.include_router(admin_transactions.router)
app.include_router(admin_users.router)
app.include_router(admin_settings.router)
app.include_router(admin_audit.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest tests/saas/test_admin_audit.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add saas/routers/admin_audit.py saas/schemas.py saas/main.py tests/saas/test_admin_audit.py
git commit -m "feat(admin): add audit log search/filter and CSV export"
```

---

### Task 10: SETUP.md update + full-suite verification

**Files:**
- Modify: `SETUP.md`
- No new test file — this task verifies the whole branch.

- [ ] **Step 1: Document the admin surface**

Append to `SETUP.md` a new section:

```markdown
## 7. Admin panel (plans, vouchers, transactions, users, settings, audit log)

1. All `/admin/*` routes require a JWT for a user whose `role` column is `admin` — promote a user by setting `role='admin'` directly in the `users` table (no self-service promotion endpoint exists, by design).
2. Creating or updating a plan via `POST/PATCH /admin/plans` automatically creates/updates the matching Stripe Product/Price using the same `STRIPE_SECRET_KEY` configured in section 6 — no manual Stripe dashboard work needed for v1.
3. Unmatched bank transfers show up at `GET /admin/transactions/unmatched`; link one to a pending order with `POST /admin/transactions/{transaction_id}/link/{order_id}`.
4. Every plan/voucher/transaction/user/setting change and every admin login is written to `audit_logs`; browse it at `GET /admin/audit` (filter by `actor_user_id`, `action`, `from_date`, `to_date`) or export with `GET /admin/audit/export.csv`.
5. Support widget IDs (Messenger Page ID, Zalo OA ID, Facebook page URL) are set via `PUT /admin/settings/{key}` — the frontend reads `GET /admin/settings` to decide which widgets to render.
```

- [ ] **Step 2: Run the full test suite**

Run: `py -m pytest -q`
Expected: all tests pass (the 127 already on `master` plus this plan's new tests)

- [ ] **Step 3: Commit**

```bash
git add SETUP.md
git commit -m "docs(admin): document admin panel setup and audit log usage"
```
