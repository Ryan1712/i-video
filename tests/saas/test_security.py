import time

import pytest

from saas.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    password_hash = hash_password("correct-password")
    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_hash_password_does_not_store_plaintext():
    password_hash = hash_password("secret123")
    assert "secret123" not in password_hash


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42, secret="test-secret")
    user_id = decode_access_token(token, secret="test-secret")
    assert user_id == 42


def test_decode_access_token_rejects_wrong_secret():
    token = create_access_token(user_id=42, secret="test-secret")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="different-secret")


def test_decode_access_token_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-real-token", secret="test-secret")


def test_create_access_token_respects_expiry():
    token = create_access_token(user_id=1, secret="s", expires_minutes=-1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="s")
