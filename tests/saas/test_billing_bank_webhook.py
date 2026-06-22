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
