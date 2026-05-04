"""RS256 JWT issuance + JWKS publication.

Choices:
  * RS256 (asymmetric) — public key can be distributed, private stays
    in Key Vault. Allows downstream services / partners to verify NexHire
    tokens without sharing the secret.
  * Single signing key (`kid` from settings). Rotation is a deploy-time
    concern in v1 — replace key, restart, JWKS endpoint reflects the
    new key. Frontend MSAL never sees these tokens; only the API does.

Token claims:
  * sub          — user_id (uuid)
  * email
  * role         — UserRole string
  * can_mentor   — bool
  * intern_id    — uuid, only for CANDIDATE tokens (RBAC scope)
  * iat / exp / iss / aud — standard
  * kid          — set in JWT header (not in claims) so JWKS lookup works
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jose import jwt

from app.config import get_settings

logger = logging.getLogger("nexhire.jwt")


@lru_cache(maxsize=1)
def _public_jwk() -> dict[str, str]:
    """Build the RFC 7517 JWK for the public key, exposed via JWKS."""
    cfg = get_settings()
    if not cfg.jwt_public_key_pem:
        raise RuntimeError("JWT_PUBLIC_KEY_PEM is not configured")

    public_key = serialization.load_pem_public_key(cfg.jwt_public_key_pem.encode("utf-8"))
    if not isinstance(public_key, RSAPublicKey):
        raise RuntimeError("Configured JWT public key is not RSA")

    numbers = public_key.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")

    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": cfg.jwt_kid,
        "n": _b64url(n_bytes),
        "e": _b64url(e_bytes),
    }


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def jwks() -> dict[str, list[dict[str, str]]]:
    """JSON document served at `/.well-known/jwks.json`."""
    return {"keys": [_public_jwk()]}


def issue_access_token(
    *,
    user_id: UUID,
    email: str,
    role: str,
    can_mentor: bool,
    intern_id: UUID | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Sign and return (access_token, expires_in_seconds)."""
    cfg = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=cfg.jwt_access_ttl_seconds)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "can_mentor": can_mentor,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": cfg.jwt_issuer,
        "aud": cfg.jwt_audience,
    }
    if intern_id is not None:
        claims["intern_id"] = str(intern_id)
    if extra_claims:
        claims.update(extra_claims)

    token = jwt.encode(
        claims,
        cfg.jwt_private_key_pem,
        algorithm="RS256",
        headers={"kid": cfg.jwt_kid},
    )
    return token, cfg.jwt_access_ttl_seconds


def issue_refresh_token() -> tuple[str, datetime]:
    """Generate an opaque refresh token (base64url, 32 bytes) and the
    matching expiry timestamp.

    The token is opaque — we hash it with bcrypt before storage and the
    `Session` row is the source of truth on validity.
    """
    import secrets

    cfg = get_settings()
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=cfg.jwt_refresh_ttl_seconds)
    return raw, expires_at
