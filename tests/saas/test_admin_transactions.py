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
