"""
AES-256-CBC encryption for third-party OAuth access_tokens / refresh_tokens.

Layout of the stored ciphertext (base64):
    base64( IV[16] || AES-CBC( PKCS7( plaintext ) ) )

The key is derived from settings.TOKEN_ENCRYPTION_KEY (base64 of 32 bytes).
Only the symmetric key is used; it never leaves the server.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from django.conf import settings

_IV_LEN = 16
_BLOCK = 128  # AES block size in bits


def _key() -> bytes:
    raw = settings.TOKEN_ENCRYPTION_KEY
    try:
        key = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        # Allow raw hex (64 chars) as a fallback for convenience.
        key = bytes.fromhex(raw)
    if len(key) != 32:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256). "
            "Generate with: python -c \"import base64,os;"
            'print(base64.b64encode(os.urandom(32)).decode())"'
        )
    return key


def encrypt_token(plaintext: str) -> str:
    """Encrypt a secret string; returns a base64 token safe to store in DB."""
    if plaintext is None:
        raise ValueError("cannot encrypt None")
    key = _key()
    iv = os.urandom(_IV_LEN)
    padder = padding.PKCS7(_BLOCK).padder()
    data = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(iv + ct).decode("ascii")


def decrypt_token(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_token`."""
    if not token:
        raise ValueError("cannot decrypt empty token")
    key = _key()
    raw = base64.b64decode(token)
    iv, ct = raw[:_IV_LEN], raw[_IV_LEN:]
    if len(iv) != _IV_LEN:
        raise ValueError("malformed token (bad IV length)")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    data = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(_BLOCK).unpadder()
    pt = unpadder.update(data) + unpadder.finalize()
    return pt.decode("utf-8")
