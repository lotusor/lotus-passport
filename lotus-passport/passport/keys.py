"""
RSA key store for RS256 signing — supports key rotation with overlapping validity.

Why a store (not a single keypair)
-----------------------------------
A unified auth center issues long-lived refresh tokens (default 14 days). If we
simply replaced the keypair on rotation, every outstanding refresh token signed
with the old key would instantly stop verifying — forcing a mass re-login. To
rotate *without* breaking active sessions we must keep the previous public key
available for verification for as long as the longest-lived token it signed can
still be valid.

Model
-----
* Keys live in ``PASSPORT_JWT_KEYS_DIR`` as ``private_<kid>.pem`` /
  ``public_<kid>.pem``, indexed by a ``manifest.json``:
      {"active_kid": "<kid>",
       "keys": [{"kid", "private", "public", "created_at"}, ...]}
* ``rotate()`` generates a fresh keypair + kid, promotes it to active, and
  prunes keys older than ``retention_days`` (default 16 ≈ refresh TTL 14d + 2d
  buffer) — so a rotated-away key can never verify a token past its natural max
  lifetime.
* ``public_pem_for_kid()`` lets the token backend pick the verifying key by the
  ``kid`` header, so old tokens keep verifying throughout the overlap window.
* The JWKS endpoint publishes every retained public key, so offline integrators
  also ride the rotation.

Explicit env PEM (``PASSPORT_JWT_PRIVATE_KEY`` / ``PUBLIC_KEY``) is supported
for secret-managed deployments: it becomes the active key with no files written
to disk.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_MANIFEST = "manifest.json"


class KeyStore:
    def __init__(self, keys_dir: str, *, initial_kid: str = "lotus-passport-rsa-1") -> None:
        self.keys_dir = keys_dir
        self.initial_kid = initial_kid
        self._manifest: dict[str, Any] | None = None
        self._env_private: str | None = None
        self._env_public: str | None = None

    # -- explicit env PEM (secret-managed deployments, no files) ------------- #
    def load_env(self, private_pem: str, public_pem: str) -> None:
        self._env_private = private_pem
        self._env_public = public_pem

    @property
    def _using_env(self) -> bool:
        return bool(self._env_private) and bool(self._env_public)

    @property
    def has_keys(self) -> bool:
        return self._using_env or os.path.exists(os.path.join(self.keys_dir, _MANIFEST))

    # -- manifest helpers ---------------------------------------------------- #
    def _read_manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            path = os.path.join(self.keys_dir, _MANIFEST)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    self._manifest = json.load(fh)
            else:
                self._manifest = {"active_kid": None, "keys": []}
        return self._manifest

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self._manifest = manifest
        os.makedirs(self.keys_dir, exist_ok=True)
        tmp = os.path.join(self.keys_dir, _MANIFEST + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
        os.replace(tmp, os.path.join(self.keys_dir, _MANIFEST))

    def _write_key_files(self, kid: str, private_pem: str, public_pem: str) -> None:
        os.makedirs(self.keys_dir, exist_ok=True)
        priv_path = os.path.join(self.keys_dir, f"private_{kid}.pem")
        pub_path = os.path.join(self.keys_dir, f"public_{kid}.pem")
        with open(priv_path, "w", encoding="utf-8") as fh:
            fh.write(private_pem)
        os.chmod(priv_path, 0o600)  # private key: owner-read only
        with open(pub_path, "w", encoding="utf-8") as fh:
            fh.write(public_pem)

    # -- public accessors ---------------------------------------------------- #
    @property
    def active_kid(self) -> str:
        if self._using_env:
            return self.initial_kid
        return self._read_manifest().get("active_kid") or self.initial_kid

    @property
    def active_private_pem(self) -> str:
        if self._using_env:
            return self._env_private  # type: ignore[return-value]
        kid = self.active_kid
        entry = self._entry(kid)
        if entry is None:
            raise RuntimeError(f"active key {kid} not found in key store")
        return self._read_pem(entry["private"])

    @property
    def active_public_pem(self) -> str:
        if self._using_env:
            return self._env_public  # type: ignore[return-value]
        kid = self.active_kid
        entry = self._entry(kid)
        if entry is None:
            raise RuntimeError(f"active key {kid} not found in key store")
        return self._read_pem(entry["public"])

    def _entry(self, kid: str) -> dict[str, Any] | None:
        for e in self._read_manifest().get("keys", []):
            if e["kid"] == kid:
                return e
        return None

    def _read_pem(self, filename: str) -> str:
        with open(os.path.join(self.keys_dir, filename), "r", encoding="utf-8") as fh:
            return fh.read()

    def public_pem_for_kid(self, kid: str | None) -> str | None:
        """Return the public PEM for ``kid``, or None if unknown/expired."""
        if not kid:
            return None
        if self._using_env:
            return self._env_public if kid == self.initial_kid else None
        entry = self._entry(kid)
        if entry is None:
            return None
        return self._read_pem(entry["public"])

    def all_public(self) -> list[tuple[str, str]]:
        """All currently-valid (kid, public_pem) pairs — for the JWKS doc."""
        if self._using_env:
            return [(self.initial_kid, self._env_public)]  # type: ignore[list-item]
        out: list[tuple[str, str]] = []
        for e in self._read_manifest().get("keys", []):
            out.append((e["kid"], self._read_pem(e["public"])))
        return out

    # -- lifecycle ----------------------------------------------------------- #
    def ensure_initial(self, kid: str | None = None, bit_length: int = 2048) -> str:
        """Generate the very first keypair (idempotent). Returns the active kid."""
        if self.has_keys and (self._using_env or self._read_manifest().get("active_kid")):
            return self.active_kid
        kid = kid or self.initial_kid
        priv, pub = self._generate(bit_length)
        self._write_key_files(kid, priv, pub)
        manifest = {
            "active_kid": kid,
            "keys": [{"kid": kid, "private": f"private_{kid}.pem",
                      "public": f"public_{kid}.pem", "created_at": time.time()}],
        }
        self._write_manifest(manifest)
        return kid

    def rotate(self, bit_length: int = 2048, retention_days: int = 16) -> str:
        """Generate a new active keypair; keep old keys for ``retention_days``.

        Returns the new active kid. Prunes keys whose age exceeds the retention
        window (never the new active one) and deletes their PEM files.
        """
        new_kid = f"lotus-passport-rsa-{int(time.time())}-{uuid.uuid4().hex[:4]}"
        priv, pub = self._generate(bit_length)
        self._write_key_files(new_kid, priv, pub)

        manifest = self._read_manifest()
        manifest["keys"].append(
            {"kid": new_kid, "private": f"private_{new_kid}.pem",
             "public": f"public_{new_kid}.pem", "created_at": time.time()}
        )
        manifest["active_kid"] = new_kid
        self._prune(manifest, retention_days)
        self._write_manifest(manifest)
        # Bust the cached active lookups.
        self._manifest = manifest
        return new_kid

    def _prune(self, manifest: dict[str, Any], retention_days: int) -> None:
        cutoff = time.time() - retention_days * 86400
        kept: list[dict[str, Any]] = []
        for e in manifest["keys"]:
            if e["kid"] == manifest.get("active_kid"):
                kept.append(e)
                continue
            if e.get("created_at", 0) < cutoff:
                for fn in (e.get("private"), e.get("public")):
                    if fn:
                        try:
                            os.remove(os.path.join(self.keys_dir, fn))
                        except OSError:  # noqa: BLE001
                            pass
            else:
                kept.append(e)
        manifest["keys"] = kept

    @staticmethod
    def _generate(bit_length: int) -> tuple[str, str]:
        key = rsa.generate_private_key(public_exponent=65537, key_size=bit_length)
        priv = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        return priv, pub
