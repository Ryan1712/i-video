"""Billing routes: Stripe checkout/webhooks and bank-transfer orders/webhooks."""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..billing.service import (
    VoucherError,
    activate_subscription,
    apply_voucher_discount,
    downgrade_to_free,
    extract_order_code,
    get_bank_webhook_secret,
    mark_past_due,
    renew_subscription,
    validate_voucher,
)
from ..billing.stripe_client import construct_webhook_event, create_checkout_session
from ..db import get_db
from ..deps import get_current_user
from ..models import BankTransaction, Order, Plan, Subscription, User
from ..schemas import (
    BankTransferRequest,
    BankTransferResponse,
    BankWebhookPayload,
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionOut,
)

router = APIRouter(prefix="/billing", tags=["billing"])


def _generate_unique_code(db: Session) -> str:
    import secrets

    while True:
        code = "OID-" + secrets.token_hex(6).upper()
        if db.query(Order).filter_by(unique_code=code).first() is None:
            return code


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    plan = db.query(Plan).filter_by(id=payload.plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.stripe_price_id is None:
        raise HTTPException(status_code=400, detail="Plan not purchasable")

    amount_cents = plan.price_cents
    promotion_code = None
    if payload.voucher_code:
        try:
            voucher = validate_voucher(db, payload.voucher_code, plan.id)
        except VoucherError as e:
            raise HTTPException(status_code=400, detail=e.code)
        amount_cents = apply_voucher_discount(amount_cents, voucher)
        promotion_code = payload.voucher_code

    order = Order(
        user_id=current_user.id, plan_id=plan.id, amount_cents=amount_cents, currency=plan.currency,
        payment_method="card", status="pending", unique_code=_generate_unique_code(db),
    )
    db.add(order)
    db.commit()

    session = create_checkout_session(
        price_id=plan.stripe_price_id,
        success_url="https://app.local/billing/success",
        cancel_url="https://app.local/billing/cancel",
        customer_email=current_user.email,
        promotion_code=promotion_code,
        metadata={"order_id": str(order.id)},
    )
    return CheckoutResponse(checkout_url=session.url)


@router.post("/orders/bank-transfer", response_model=BankTransferResponse)
def create_bank_transfer_order(
    payload: BankTransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BankTransferResponse:
    plan = db.query(Plan).filter_by(id=payload.plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    amount_cents = plan.price_cents
    if payload.voucher_code:
        try:
            voucher = validate_voucher(db, payload.voucher_code, plan.id)
        except VoucherError as e:
            raise HTTPException(status_code=400, detail=e.code)
        amount_cents = apply_voucher_discount(amount_cents, voucher)

    unique_code = _generate_unique_code(db)
    order = Order(
        user_id=current_user.id, plan_id=plan.id, amount_cents=amount_cents, currency=plan.currency,
        payment_method="bank_transfer", status="pending", unique_code=unique_code,
    )
    db.add(order)
    db.commit()

    qr_payload = f"bank:whatif|amount:{amount_cents}|content:{unique_code}"
    return BankTransferResponse(
        order_id=order.id, unique_code=unique_code, amount_cents=amount_cents,
        bank_account_qr_payload=qr_payload,
    )


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="stripe-signature"),
    db: Session = Depends(get_db),
) -> dict:
    payload = await request.body()
    try:
        event = construct_webhook_event(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        order_id = int(data["metadata"]["order_id"])
        order = db.query(Order).filter_by(id=order_id).one_or_none()
        if order is not None:
            activate_subscription(db, order)
    elif event_type == "invoice.payment_succeeded":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["subscription"]).one_or_none()
        if sub is not None:
            renew_subscription(db, sub, datetime.datetime.utcnow() + datetime.timedelta(days=30))
    elif event_type == "invoice.payment_failed":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["subscription"]).one_or_none()
        if sub is not None:
            mark_past_due(db, sub)
    elif event_type == "customer.subscription.deleted":
        sub = db.query(Subscription).filter_by(stripe_subscription_id=data["id"]).one_or_none()
        if sub is not None:
            free_plan = db.query(Plan).filter_by(price_cents=0).first()
            if free_plan is not None:
                downgrade_to_free(db, sub, free_plan)

    return {"received": True}


@router.post("/webhooks/bank")
def bank_webhook(
    payload: BankWebhookPayload,
    x_webhook_secret: str = Header(...),
    db: Session = Depends(get_db),
) -> dict:
    if x_webhook_secret != get_bank_webhook_secret():
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    existing = db.query(BankTransaction).filter_by(gateway_transaction_id=payload.gateway_transaction_id).one_or_none()
    if existing is not None:
        return {"received": True, "duplicate": True}

    order_code = extract_order_code(payload.content)
    matched_order = None
    if order_code is not None:
        candidate = db.query(Order).filter_by(unique_code=order_code, status="pending").one_or_none()
        if candidate is not None and candidate.amount_cents == payload.amount_cents:
            matched_order = candidate

    txn = BankTransaction(
        gateway_transaction_id=payload.gateway_transaction_id,
        amount_cents=payload.amount_cents,
        content=payload.content,
        received_at=payload.received_at,
        status="matched" if matched_order else "unmatched",
        matched_order_id=matched_order.id if matched_order else None,
    )
    db.add(txn)
    db.commit()

    if matched_order is not None:
        activate_subscription(db, matched_order)

    return {"received": True}


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Subscription:
    subscription = db.query(Subscription).filter_by(user_id=current_user.id).one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription")
    return subscription
