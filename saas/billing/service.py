"""Payment-method-agnostic billing logic shared by the Stripe and bank-transfer flows."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from ..models import Order, Plan, Subscription, Voucher


class VoucherError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def activate_subscription(db: Session, order: Order) -> Subscription:
    subscription = (
        db.query(Subscription)
        .filter_by(user_id=order.user_id, plan_id=order.plan_id)
        .one_or_none()
    )
    if subscription is None:
        subscription = Subscription(user_id=order.user_id, plan_id=order.plan_id)
        db.add(subscription)

    subscription.status = "active"
    order.status = "paid"
    order.paid_at = datetime.datetime.utcnow()
    db.commit()
    return subscription


def renew_subscription(db: Session, subscription: Subscription, new_period_end: datetime.datetime) -> Subscription:
    subscription.status = "active"
    subscription.current_period_end = new_period_end
    db.commit()
    return subscription


def mark_past_due(db: Session, subscription: Subscription) -> Subscription:
    subscription.status = "past_due"
    db.commit()
    return subscription


def downgrade_to_free(db: Session, subscription: Subscription, free_plan: Plan) -> Subscription:
    subscription.plan_id = free_plan.id
    subscription.status = "active"
    db.commit()
    return subscription


def validate_voucher(db: Session, code: str, plan_id: int) -> Voucher:
    voucher = db.query(Voucher).filter_by(code=code).one_or_none()
    if voucher is None:
        raise VoucherError("ERR_VOUCHER_INVALID")
    if plan_id not in (voucher.applicable_plan_ids or []):
        raise VoucherError("ERR_VOUCHER_INVALID")
    if voucher.used_count >= voucher.max_uses:
        raise VoucherError("ERR_VOUCHER_INVALID")
    if voucher.expires_at is not None and voucher.expires_at < datetime.datetime.utcnow():
        raise VoucherError("ERR_VOUCHER_EXPIRED")
    return voucher


def apply_voucher_discount(amount_cents: int, voucher: Voucher) -> int:
    if voucher.discount_type == "percent":
        discount = amount_cents * voucher.discount_value // 100
    else:
        discount = voucher.discount_value
    return max(0, amount_cents - discount)


def expire_stale_orders(db: Session, max_age_minutes: int = 30) -> int:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=max_age_minutes)
    stale_orders = (
        db.query(Order)
        .filter(Order.status == "pending", Order.created_at < cutoff)
        .all()
    )
    for order in stale_orders:
        order.status = "expired"
    db.commit()
    return len(stale_orders)
