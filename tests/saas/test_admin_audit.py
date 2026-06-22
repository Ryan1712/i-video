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
