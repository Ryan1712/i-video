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
