import datetime

import pytest

from saas.billing.service import (
    VoucherError,
    activate_subscription,
    apply_voucher_discount,
    downgrade_to_free,
    expire_stale_orders,
    mark_past_due,
    renew_subscription,
    validate_voucher,
)
from saas.models import Order, Plan, Subscription, User, Voucher


def _make_user_and_plan(db_session):
    user = User(email="u@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()
    return user, plan


def test_activate_subscription_creates_active_subscription(db_session):
    user, plan = _make_user_and_plan(db_session)
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-1",
    )
    db_session.add(order)
    db_session.commit()

    sub = activate_subscription(db_session, order)

    assert sub.user_id == user.id
    assert sub.plan_id == plan.id
    assert sub.status == "active"
    refreshed_order = db_session.query(Order).filter_by(id=order.id).one()
    assert refreshed_order.status == "paid"
    assert refreshed_order.paid_at is not None


def test_activate_subscription_reuses_existing_subscription_row(db_session):
    user, plan = _make_user_and_plan(db_session)
    existing = Subscription(user_id=user.id, plan_id=plan.id, status="past_due")
    db_session.add(existing)
    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=199000, currency="VND",
        payment_method="card", status="pending", unique_code="OID-2",
    )
    db_session.add(order)
    db_session.commit()

    sub = activate_subscription(db_session, order)

    assert sub.id == existing.id
    assert sub.status == "active"
    assert db_session.query(Subscription).count() == 1


def test_renew_subscription_updates_period_end(db_session):
    user, plan = _make_user_and_plan(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active")
    db_session.add(sub)
    db_session.commit()

    new_end = datetime.datetime(2026, 7, 1)
    renewed = renew_subscription(db_session, sub, new_end)

    assert renewed.current_period_end == new_end
    assert renewed.status == "active"


def test_mark_past_due(db_session):
    user, plan = _make_user_and_plan(db_session)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="active")
    db_session.add(sub)
    db_session.commit()

    updated = mark_past_due(db_session, sub)
    assert updated.status == "past_due"


def test_downgrade_to_free(db_session):
    user, plan = _make_user_and_plan(db_session)
    free_plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add(free_plan)
    sub = Subscription(user_id=user.id, plan_id=plan.id, status="past_due")
    db_session.add(sub)
    db_session.commit()

    updated = downgrade_to_free(db_session, sub, free_plan)
    assert updated.plan_id == free_plan.id
    assert updated.status == "active"


def test_validate_voucher_rejects_expired(db_session):
    _, plan = _make_user_and_plan(db_session)
    voucher = Voucher(
        code="OLD10", discount_type="percent", discount_value=10, max_uses=10,
        expires_at=datetime.datetime(2020, 1, 1), applicable_plan_ids=[plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "OLD10", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_EXPIRED"


def test_validate_voucher_rejects_unknown_code(db_session):
    _, plan = _make_user_and_plan(db_session)
    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "NOPE", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_validate_voucher_rejects_wrong_plan(db_session):
    _, plan = _make_user_and_plan(db_session)
    other_plan = Plan(name="Other", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add(other_plan)
    db_session.commit()
    voucher = Voucher(
        code="ONLYOTHER", discount_type="percent", discount_value=10, max_uses=10,
        applicable_plan_ids=[other_plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "ONLYOTHER", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_validate_voucher_rejects_exhausted(db_session):
    _, plan = _make_user_and_plan(db_session)
    voucher = Voucher(
        code="USED", discount_type="percent", discount_value=10, max_uses=1, used_count=1,
        applicable_plan_ids=[plan.id],
    )
    db_session.add(voucher)
    db_session.commit()

    with pytest.raises(VoucherError) as exc_info:
        validate_voucher(db_session, "USED", plan.id)
    assert exc_info.value.code == "ERR_VOUCHER_INVALID"


def test_apply_voucher_discount_percent():
    voucher = Voucher(code="P10", discount_type="percent", discount_value=10, applicable_plan_ids=[])
    assert apply_voucher_discount(100000, voucher) == 90000


def test_apply_voucher_discount_fixed():
    voucher = Voucher(code="F5000", discount_type="fixed", discount_value=5000, applicable_plan_ids=[])
    assert apply_voucher_discount(100000, voucher) == 95000


def test_apply_voucher_discount_never_negative():
    voucher = Voucher(code="BIG", discount_type="fixed", discount_value=999999, applicable_plan_ids=[])
    assert apply_voucher_discount(1000, voucher) == 0


def test_expire_stale_orders(db_session):
    user, plan = _make_user_and_plan(db_session)
    stale = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=1000, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-OLD",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=45),
    )
    fresh = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=1000, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-NEW",
        created_at=datetime.datetime.utcnow(),
    )
    db_session.add_all([stale, fresh])
    db_session.commit()

    count = expire_stale_orders(db_session, max_age_minutes=30)

    assert count == 1
    assert db_session.query(Order).filter_by(unique_code="OID-OLD").one().status == "expired"
    assert db_session.query(Order).filter_by(unique_code="OID-NEW").one().status == "pending"
