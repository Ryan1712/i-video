from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from saas.db import Base, get_db
from saas.main import app
from saas.models import Order, Plan, User, Voucher
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


def test_checkout_rejects_plan_without_stripe_price_id(db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", stripe_price_id=None, trial_days=0, limits={})
    db_session.add(plan)
    db_session.commit()

    client, token, user = _client_and_token(db_session_factory, db_session)

    response = client.post(
        "/billing/checkout",
        json={"plan_id": plan.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
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


@patch("saas.routers.billing.create_checkout_session")
def test_checkout_applies_voucher_discount_to_order_amount(mock_create_session, db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    plan = Plan(name="Pro", price_cents=200000, currency="VND", billing_interval="month", stripe_price_id="price_pro", trial_days=0, limits={})
    db_session.add(plan)
    db_session.commit()
    voucher = Voucher(
        code="SAVE10", discount_type="percent", discount_value=10,
        max_uses=5, used_count=0, applicable_plan_ids=[plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    client, token, user = _client_and_token(db_session_factory, db_session)
    mock_create_session.return_value = MagicMock(url="https://checkout.stripe.com/cs_test_voucher")

    response = client.post(
        "/billing/checkout",
        json={"plan_id": plan.id, "voucher_code": "SAVE10"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    order = db_session.query(Order).filter_by(user_id=user.id, plan_id=plan.id).one()
    assert order.amount_cents == 180000
    app.dependency_overrides.clear()
