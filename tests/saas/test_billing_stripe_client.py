from unittest.mock import MagicMock, patch

import pytest

from saas.billing.stripe_client import (
    construct_webhook_event,
    create_checkout_session,
    get_stripe_secret_key,
    get_stripe_webhook_secret,
)


def test_get_stripe_secret_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        get_stripe_secret_key()


def test_get_stripe_webhook_secret_raises_when_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        get_stripe_webhook_secret()


@patch("saas.billing.stripe_client.stripe.checkout.Session.create")
def test_create_checkout_session_calls_stripe_sdk(mock_create, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    mock_create.return_value = MagicMock(id="cs_test_1", url="https://checkout.stripe.com/cs_test_1")

    session = create_checkout_session(
        price_id="price_123", success_url="https://app/success", cancel_url="https://app/cancel",
        customer_email="user@x.com",
    )

    assert session.id == "cs_test_1"
    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert kwargs["customer_email"] == "user@x.com"
    assert kwargs["mode"] == "subscription"


@patch("saas.billing.stripe_client.stripe.Webhook.construct_event")
def test_construct_webhook_event_calls_stripe_sdk(mock_construct, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_123")
    mock_construct.return_value = {"type": "checkout.session.completed"}

    event = construct_webhook_event(b"payload", "sig_header_value")

    assert event["type"] == "checkout.session.completed"
    mock_construct.assert_called_once_with(b"payload", "sig_header_value", "whsec_123")
