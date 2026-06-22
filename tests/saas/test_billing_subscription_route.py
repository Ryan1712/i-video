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
