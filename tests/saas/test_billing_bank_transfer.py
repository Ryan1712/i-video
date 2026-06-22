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
