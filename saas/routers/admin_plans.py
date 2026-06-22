"""Admin plan management: CRUD with automatic Stripe Product/Price sync."""
from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..admin_deps import require_admin
from ..audit import log_action
from ..billing.stripe_client import create_price, create_product, get_stripe_secret_key
from ..db import get_db
from ..models import Plan, User
from ..schemas import PlanIn, PlanOut

router = APIRouter(prefix="/admin/plans", tags=["admin"])


@router.post("", response_model=PlanOut, status_code=201)
def create_plan(
    payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Plan:
    product = create_product(payload.name)
    price = create_price(product.id, payload.price_cents, payload.currency, payload.billing_interval)

    plan = Plan(
        name=payload.name, price_cents=payload.price_cents, currency=payload.currency,
        billing_interval=payload.billing_interval, stripe_price_id=price.id,
        trial_days=payload.trial_days, limits=payload.limits,
    )
    db.add(plan)
    db.commit()

    log_action(
        db, actor=current_user, action="plan.create", target_type="plan", target_id=plan.id,
        after={"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id},
    )
    return plan


@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Plan]:
    return db.query(Plan).all()


@router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(
    plan_id: int, payload: PlanIn, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
) -> Plan:
    plan = db.query(Plan).filter_by(id=plan_id).one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    before = {"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id}

    price_changed = payload.price_cents != plan.price_cents or payload.billing_interval != plan.billing_interval
    if price_changed and plan.stripe_price_id is not None:
        stripe.api_key = get_stripe_secret_key()
        existing_price = stripe.Price.retrieve(plan.stripe_price_id)
        new_price = create_price(existing_price.product, payload.price_cents, payload.currency, payload.billing_interval)
        plan.stripe_price_id = new_price.id

    plan.name = payload.name
    plan.price_cents = payload.price_cents
    plan.currency = payload.currency
    plan.billing_interval = payload.billing_interval
    plan.trial_days = payload.trial_days
    plan.limits = payload.limits
    db.commit()

    log_action(
        db, actor=current_user, action="plan.update", target_type="plan", target_id=plan.id,
        before=before, after={"name": plan.name, "price_cents": plan.price_cents, "stripe_price_id": plan.stripe_price_id},
    )
    return plan
