"""Tests for AES-256-CBC token encryption (passport.crypto)."""
import base64
import os

import pytest
from django.test import override_settings

from passport import crypto


def test_encrypt_decrypt_roundtrip():
    ct = crypto.encrypt_token("secret-access-token")
    assert crypto.decrypt_token(ct) == "secret-access-token"


def test_ciphertext_is_random_per_call():
    a = crypto.encrypt_token("same-plaintext")
    b = crypto.encrypt_token("same-plaintext")
    assert a != b  # random IV
    assert crypto.decrypt_token(a) == crypto.decrypt_token(b)


def test_decrypt_with_wrong_key_raises():
    ct = crypto.encrypt_token("top-secret")
    wrong = base64.b64encode(b"2" * 32).decode()
    with override_settings(TOKEN_ENCRYPTION_KEY=wrong):
        with pytest.raises(ValueError):
            crypto.decrypt_token(ct)


def test_empty_token_raises():
    with pytest.raises(ValueError):
        crypto.decrypt_token("")


def test_key_must_be_32_bytes():
    bad = base64.b64encode(b"too-short").decode()
    with override_settings(TOKEN_ENCRYPTION_KEY=bad):
        with pytest.raises(ValueError):
            crypto.encrypt_token("x")
