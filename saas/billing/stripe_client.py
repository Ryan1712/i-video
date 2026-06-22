"""Thin wrapper around the Stripe SDK so the rest of the app never imports `stripe` directly."""
from __future__ import annotations

import os

import stripe


def get_stripe_secret_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY environment variable is not set")
    return key


def get_stripe_webhook_secret() -> str:
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET environment variable is not set")
    return secret


def create_checkout_session(
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    promotion_code: str | None = None,
    metadata: dict | None = None,
) -> stripe.checkout.Session:
    stripe.api_key = get_stripe_secret_key()
    kwargs = dict(
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
    )
    if promotion_code:
        kwargs["discounts"] = [{"promotion_code": promotion_code}]
    if metadata:
        kwargs["metadata"] = metadata
    return stripe.checkout.Session.create(**kwargs)


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    secret = get_stripe_webhook_secret()
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def create_product(name: str) -> stripe.Product:
    stripe.api_key = get_stripe_secret_key()
    return stripe.Product.create(name=name)


def create_price(product_id: str, price_cents: int, currency: str, billing_interval: str) -> stripe.Price:
    stripe.api_key = get_stripe_secret_key()
    return stripe.Price.create(
        product=product_id, unit_amount=price_cents, currency=currency.lower(),
        recurring={"interval": billing_interval},
    )
