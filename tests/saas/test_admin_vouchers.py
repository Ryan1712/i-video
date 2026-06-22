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
