"""Azure Key Vault secret resolver.

Lazy + cached. Two reasons it's lazy:
  1. Local dev usually has no Key Vault — the codebase must import
     cleanly without it.
  2. `DefaultAzureCredential` is expensive to instantiate; we want one
     instance per process, not per call.

Convention used by `app.config.Settings`:
  * Plain env value (e.g. `JWT_PRIVATE_KEY_PEM=-----BEGIN…`) → used as-is.
  * Vault reference (e.g. `JWT_PRIVATE_KEY_PEM=kvref:nexhire-jwt-private`)
    → resolved on first read against `AZURE_KEY_VAULT_URL`.

For S0 we provide the resolver; the resolution-on-read wiring lives in
`config.py` only when we actually need a real secret (S0.5 auth uses
`JWT_PRIVATE_KEY_PEM` for token signing — that's where it kicks in).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from azure.keyvault.secrets.aio import SecretClient

logger = logging.getLogger("nexhire.keyvault")

KVREF_PREFIX = "kvref:"


@lru_cache(maxsize=1)
def _get_credential() -> object:
    """Single `DefaultAzureCredential` per process."""
    from azure.identity.aio import DefaultAzureCredential

    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _get_client() -> "SecretClient":
    from azure.keyvault.secrets.aio import SecretClient

    cfg = get_settings()
    if not cfg.azure_key_vault_url:
        raise RuntimeError("AZURE_KEY_VAULT_URL is not configured")
    return SecretClient(vault_url=cfg.azure_key_vault_url, credential=_get_credential())


# In-memory cache. Secrets do not change at runtime; for a rotation we
# restart the app. Acceptable trade-off — Azure Key Vault GETs are cheap
# but not free, and we don't want a deploy to fan out hundreds of calls.
_secret_cache: dict[str, str] = {}


async def resolve(value: str) -> str:
    """Resolve a config value through Key Vault if it's a kvref.

    Idempotent: plain values pass through. Cached on first lookup.
    """
    if not value or not value.startswith(KVREF_PREFIX):
        return value

    secret_name = value.removeprefix(KVREF_PREFIX)
    if secret_name in _secret_cache:
        return _secret_cache[secret_name]

    client = _get_client()
    try:
        kv_secret = await client.get_secret(secret_name)
    except Exception as exc:
        logger.exception(
            "nexhire.keyvault.fetch_failed",
            extra={"secret_name": secret_name},
        )
        raise RuntimeError(f"Could not resolve Key Vault secret {secret_name!r}") from exc

    secret_value = kv_secret.value or ""
    _secret_cache[secret_name] = secret_value
    return secret_value


async def close() -> None:
    """Close the Key Vault client + credential. Called on shutdown."""
    if _get_client.cache_info().currsize:
        client = _get_client()
        await client.close()
    if _get_credential.cache_info().currsize:
        credential = _get_credential()
        if hasattr(credential, "close"):
            await credential.close()  # type: ignore[func-returns-value]
