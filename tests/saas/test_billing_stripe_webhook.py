from unittest.mock import patch

from fastapi.testclient import TestClient

from saas.db import get_db
from saas.main import app
import datetime

from saas.models import Order, Plan, Subscription, User


def _setup(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    user = User(email="webhook@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", stripe_price_id="price_pro", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-STRIPE-1",
    )
    db_session.add(order)
    db_session.commit()
    return user, plan, order


@patch("saas.routers.billing.construct_webhook_event")
def test_checkout_completed_activates_subscription(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    mock_construct.return_value = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"order_id": str(order.id)}}},
    }
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    assert db_session.query(Subscription).filter_by(user_id=user.id).one().status == "active"
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_invoice_payment_failed_marks_past_due(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active", stripe_subscription_id="sub_123")
    db_session.add(sub)
    db_session.commit()

    mock_construct.return_value = {
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_123"}},
    }
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    assert db_session.query(Subscription).filter_by(id=sub.id).one().status == "past_due"
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_invoice_payment_succeeded_renews_subscription(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="past_due", stripe_subscription_id="sub_456")
    db_session.add(sub)
    db_session.commit()

    mock_construct.return_value = {
        "type": "invoice.payment_succeeded",
        "data": {"object": {"subscription": "sub_456"}},
    }
    client = TestClient(app)

    before = datetime.datetime.utcnow()
    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    updated = db_session.query(Subscription).filter_by(id=sub.id).one()
    assert updated.status == "active"
    assert updated.current_period_end is not None
    assert updated.current_period_end > before
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_customer_subscription_deleted_downgrades_to_free(mock_construct, db_session_factory, db_session):
    user, plan, order = _setup(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active", stripe_subscription_id="sub_789")
    db_session.add(sub)
    free_plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", stripe_price_id="price_free", trial_days=0, limits={})
    db_session.add(free_plan)
    db_session.commit()

    mock_construct.return_value = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_789"}},
    }
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "sig"},
    )

    assert response.status_code == 200
    updated = db_session.query(Subscription).filter_by(id=sub.id).one()
    assert updated.plan_id == free_plan.id
    app.dependency_overrides.clear()


@patch("saas.routers.billing.construct_webhook_event")
def test_invalid_signature_rejected(mock_construct, db_session_factory, db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    mock_construct.side_effect = ValueError("Invalid signature")
    client = TestClient(app)

    response = client.post(
        "/billing/webhooks/stripe", content=b"{}", headers={"stripe-signature": "bad"},
    )

    assert response.status_code == 400
    app.dependency_overrides.clear()
