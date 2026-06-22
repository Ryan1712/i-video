import datetime

from saas.models import BankTransaction, Order, Plan, Subscription, User, Voucher


def test_plan_round_trip(db_session):
    plan = Plan(
        name="Pro", price_cents=199000, currency="VND", billing_interval="month",
        stripe_price_id="price_test_123", trial_days=7, limits={"episodes_per_month": 10},
    )
    db_session.add(plan)
    db_session.commit()

    fetched = db_session.query(Plan).filter_by(name="Pro").one()
    assert fetched.price_cents == 199000
    assert fetched.limits == {"episodes_per_month": 10}


def test_subscription_links_user_and_plan(db_session):
    user = User(email="a@x.com", password_hash="h")
    plan = Plan(name="Free", price_cents=0, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    sub = Subscription(user_id=user.id, plan_id=plan.id, status="trialing")
    db_session.add(sub)
    db_session.commit()

    fetched = db_session.query(Subscription).one()
    assert fetched.user_id == user.id
    assert fetched.plan_id == plan.id
    assert fetched.status == "trialing"


def test_order_and_voucher(db_session):
    user = User(email="b@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=199000, currency="VND", billing_interval="month", trial_days=0, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    voucher = Voucher(code="SALE10", discount_type="percent", discount_value=10, max_uses=100, applicable_plan_ids=[plan.id])
    db_session.add(voucher)
    db_session.commit()

    order = Order(
        user_id=user.id, plan_id=plan.id, amount_cents=179100, currency="VND",
        payment_method="bank_transfer", status="pending", unique_code="OID-ABC123", voucher_id=voucher.id,
    )
    db_session.add(order)
    db_session.commit()

    fetched = db_session.query(Order).one()
    assert fetched.voucher_id == voucher.id
    assert fetched.unique_code == "OID-ABC123"


def test_bank_transaction_unique_gateway_id(db_session):
    txn = BankTransaction(
        gateway_transaction_id="GW-1", amount_cents=179100, content="OID-ABC123 payment",
        received_at=datetime.datetime.utcnow(), status="unmatched",
    )
    db_session.add(txn)
    db_session.commit()

    fetched = db_session.query(BankTransaction).one()
    assert fetched.status == "unmatched"
    assert fetched.matched_order_id is None


def test_user_has_used_trial_defaults_false(db_session):
    user = User(email="c@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    assert db_session.query(User).one().has_used_trial is False
