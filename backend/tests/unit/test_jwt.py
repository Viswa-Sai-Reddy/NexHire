"""JWT issue + verify roundtrip — no DB, no HTTP."""
from __future__ import annotations

from uuid import uuid4

import pytest
from jose import jwt

from app.config import Settings
from app.modules.auth import jwt_service
from app.shared.constants import UserRole


@pytest.fixture
def populated_settings(test_settings: Settings) -> Settings:
    """Re-export with explicit type so tests get the fixture's settings."""
    return test_settings


def test_jwks_contains_one_public_key(populated_settings: Settings) -> None:
    payload = jwt_service.jwks()
    assert "keys" in payload
    keys = payload["keys"]
    assert len(keys) == 1
    key = keys[0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["kid"] == populated_settings.jwt_kid


def test_access_token_roundtrip(populated_settings: Settings) -> None:
    user_id = uuid4()
    token, ttl = jwt_service.issue_access_token(
        user_id=user_id,
        email="alice@example.com",
        role=UserRole.HR.value,
        can_mentor=True,
    )
    assert ttl == populated_settings.jwt_access_ttl_seconds

    # Verify with the public key.
    claims = jwt.decode(
        token,
        populated_settings.jwt_public_key_pem,
        algorithms=["RS256"],
        audience=populated_settings.jwt_audience,
        issuer=populated_settings.jwt_issuer,
    )
    assert claims["sub"] == str(user_id)
    assert claims["email"] == "alice@example.com"
    assert claims["role"] == "HR"
    assert claims["can_mentor"] is True


def test_refresh_token_unique() -> None:
    a, _ = jwt_service.issue_refresh_token()
    b, _ = jwt_service.issue_refresh_token()
    assert a != b
    assert len(a) > 30
