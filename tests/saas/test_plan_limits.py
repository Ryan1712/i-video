import datetime

from saas.billing.limits import PlanLimitError, check_episode_limit
from saas.models import Episode, Plan, Subscription, User


def test_no_subscription_means_unlimited(db_session):
    user = User(email="nolimit@x.com", password_hash="h")
    db_session.add(user)
    db_session.commit()

    check_episode_limit(db_session, user)  # should not raise


def test_under_limit_allows_creation(db_session):
    user = User(email="under@x.com", password_hash="h")
    plan = Plan(name="Pro", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 5})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.add(Episode(user_id=user.id, title="ep1"))
    db_session.commit()

    check_episode_limit(db_session, user)  # 1 < 5, should not raise


def test_at_limit_rejects_creation(db_session):
    user = User(email="atlimit@x.com", password_hash="h")
    plan = Plan(name="Starter", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 1})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    db_session.add(Episode(user_id=user.id, title="ep1"))
    db_session.commit()

    try:
        check_episode_limit(db_session, user)
        assert False, "expected PlanLimitError"
    except PlanLimitError as e:
        assert e.code == "ERR_PLAN_LIMIT_REACHED"


def test_old_episodes_outside_window_dont_count(db_session):
    user = User(email="old@x.com", password_hash="h")
    plan = Plan(name="Starter", price_cents=1, currency="VND", billing_interval="month", trial_days=0, limits={"episodes_per_month": 1})
    db_session.add_all([user, plan])
    db_session.commit()
    db_session.add(Subscription(user_id=user.id, plan_id=plan.id, status="active"))
    old_episode = Episode(
        user_id=user.id, title="ep_old",
        created_at=datetime.datetime.utcnow() - datetime.timedelta(days=40),
    )
    db_session.add(old_episode)
    db_session.commit()

    check_episode_limit(db_session, user)  # outside 30-day window, should not raise
