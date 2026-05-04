"""Azure AD ID-token validation (server-side companion to MSAL on the SPA).

Flow:
  1. Frontend MSAL completes the OIDC dance against Azure AD and gets
     an ID token + access token. We don't need the access token here.
  2. SPA POSTs the ID token to /auth/login.
  3. We validate the ID token against Microsoft's JWKS (cached), then
     find or create the user record, then issue our own NexHire JWT.

Caching:
  * Microsoft's JWKS endpoint is fetched once and cached for 24h. The
    `kid` in the incoming token is matched against the cache; on miss
    we refetch (rotation lands within minutes).
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any, cast

import httpx
from jose import JWTError, jwk, jwt

from app.config import get_settings
from app.shared.exceptions import SsoTokenInvalidError

logger = logging.getLogger("nexhire.azure_ad")

JWKS_TTL_SECONDS = 24 * 3_600

# In-memory cache: (jwks_dict, fetched_at_unix).
_jwks_cache: tuple[dict[str, Any], float] | None = None


@lru_cache(maxsize=1)
def _jwks_url() -> str:
    cfg = get_settings()
    return f"https://login.microsoftonline.com/{cfg.azure_ad_tenant_id}/discovery/v2.0/keys"


async def _get_jwks(*, force: bool = False) -> dict[str, Any]:
    global _jwks_cache
    now = time.time()
    if not force and _jwks_cache and now - _jwks_cache[1] < JWKS_TTL_SECONDS:
        return _jwks_cache[0]

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(_jwks_url())
        response.raise_for_status()
        data = response.json()
    _jwks_cache = (data, now)
    return data


async def validate_id_token(id_token: str) -> dict[str, Any]:
    """Validate an Azure AD ID token. Returns the claims dict.

    Raises:
        SsoTokenInvalidError: any failure path.
    """
    cfg = get_settings()
    if not cfg.azure_ad_tenant_id or not cfg.azure_ad_client_id:
        raise SsoTokenInvalidError(user_message="Azure AD is not configured.")

    try:
        unverified_header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise SsoTokenInvalidError() from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise SsoTokenInvalidError(user_message="Missing 'kid' in ID token header.")

    keys = (await _get_jwks())["keys"]
    matching = next((k for k in keys if k["kid"] == kid), None)
    if matching is None:
        # Maybe rotated — refetch once.
        keys = (await _get_jwks(force=True))["keys"]
        matching = next((k for k in keys if k["kid"] == kid), None)
    if matching is None:
        raise SsoTokenInvalidError(user_message="Unknown signing key.")

    public_key = jwk.construct(matching, algorithm="RS256")

    try:
        claims = jwt.decode(
            id_token,
            cast(str, public_key.to_pem().decode("ascii")),
            algorithms=["RS256"],
            audience=cfg.azure_ad_client_id,
            issuer=f"https://login.microsoftonline.com/{cfg.azure_ad_tenant_id}/v2.0",
        )
    except JWTError as exc:
        logger.warning("nexhire.azure_ad.token_invalid", extra={"reason": str(exc)})
        raise SsoTokenInvalidError() from exc

    return claims
