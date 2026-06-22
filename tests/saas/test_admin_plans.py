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


@patch("saas.routers.admin_plans.stripe.Price.retrieve")
@patch("saas.routers.admin_plans.create_price")
def test_update_plan_price_creates_new_stripe_price(mock_create_price, mock_retrieve, db_session_factory, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-test-secret")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    app.dependency_overrides[get_db] = lambda: db_session
    admin, token = _admin_token(db_session)
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", stripe_price_id="price_old", trial_days=7, limits={})
    db_session.add(plan)
    db_session.commit()
    mock_retrieve.return_value = MagicMock(product="prod_old")
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
