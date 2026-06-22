import pytest

from saas.billing.service import TrialError, start_trial
from saas.models import Plan, Subscription, User


def test_start_trial_creates_trialing_subscription(db_session):
    user = User(email="trial@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=7, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    sub = start_trial(db_session, user, plan)

    assert sub.status == "trialing"
    assert sub.current_period_end is not None
    assert db_session.query(User).filter_by(id=user.id).one().has_used_trial is True


def test_start_trial_rejects_repeat_trial(db_session):
    user = User(email="trial2@x.com", password_hash="h", has_used_trial=True)
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=7, limits={})
    db_session.add_all([user, plan])
    db_session.commit()

    with pytest.raises(TrialError) as exc_info:
        start_trial(db_session, user, plan)
    assert exc_info.value.code == "ERR_TRIAL_ALREADY_USED"
