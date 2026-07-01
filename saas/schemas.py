"""Pydantic request/response models for the SaaS API."""
from __future__ import annotations

import datetime

from pydantic import BaseModel


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SceneIn(BaseModel):
    narration_text: str


class SceneOut(BaseModel):
    id: int
    order_index: int
    narration_text: str
    asset_object_key: str | None

    class Config:
        from_attributes = True


class EpisodeIn(BaseModel):
    title: str
    description: str = ""
    tags: str = ""
    scenes: list[SceneIn] = []


class EpisodeOut(BaseModel):
    id: int
    title: str
    description: str
    tags: str
    status: str
    output_object_key: str | None
    scenes: list[SceneOut]

    class Config:
        from_attributes = True


class AssetUrlOut(BaseModel):
    url: str


class OutputUrlOut(BaseModel):
    url: str


class JobOut(BaseModel):
    id: int
    status: str
    progress_pct: int
    error_message: str | None

    class Config:
        from_attributes = True


class CheckoutRequest(BaseModel):
    plan_id: int
    voucher_code: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str


class BankTransferRequest(BaseModel):
    plan_id: int
    voucher_code: str | None = None


class BankTransferResponse(BaseModel):
    order_id: int
    unique_code: str
    amount_cents: int
    bank_account_qr_payload: str


class BankWebhookPayload(BaseModel):
    gateway_transaction_id: str
    amount_cents: int
    content: str
    received_at: datetime.datetime


class SubscriptionOut(BaseModel):
    plan_id: int
    status: str
    current_period_end: datetime.datetime | None

    class Config:
        from_attributes = True


class PlanIn(BaseModel):
    name: str
    price_cents: int
    currency: str = "VND"
    billing_interval: str = "month"
    trial_days: int = 0
    limits: dict = {}


class PlanOut(BaseModel):
    id: int
    name: str
    price_cents: int
    currency: str
    billing_interval: str
    stripe_price_id: str | None
    trial_days: int
    limits: dict

    class Config:
        from_attributes = True


class BankTransactionOut(BaseModel):
    id: int
    gateway_transaction_id: str
    amount_cents: int
    content: str
    received_at: datetime.datetime
    status: str
    matched_order_id: int | None

    class Config:
        from_attributes = True


class VoucherIn(BaseModel):
    code: str
    discount_type: str
    discount_value: int
    max_uses: int = 1
    expires_at: datetime.datetime | None = None
    applicable_plan_ids: list[int] = []


class VoucherOut(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: int
    max_uses: int
    used_count: int
    expires_at: datetime.datetime | None
    applicable_plan_ids: list[int]

    class Config:
        from_attributes = True


class SiteSettingIn(BaseModel):
    value: str


class SiteSettingOut(BaseModel):
    key: str
    value: str

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    is_suspended: bool
    plan_name: str | None


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int
    actor_role: str
    action: str
    target_type: str
    target_id: int
    before_data: dict | None
    after_data: dict | None
    ip_address: str | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True
