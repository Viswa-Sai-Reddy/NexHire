"""Azure Blob Storage client wrapper.

S0 ships a minimal singleton + the shape of upload + SAS generation that
the rest of the codebase expects. S1 fleshes out the upload pipeline
(virus scan via Azure Defender, deterministic key generation, retention
policy hooks).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import uuid4

from app.config import get_settings
from app.shared.exceptions import AzureBlobError

if TYPE_CHECKING:
    from azure.storage.blob.aio import BlobServiceClient

logger = logging.getLogger("nexhire.blob")


@lru_cache(maxsize=1)
def _credential() -> object:
    from azure.identity.aio import DefaultAzureCredential

    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_client() -> "BlobServiceClient":
    from azure.storage.blob.aio import BlobServiceClient

    cfg = get_settings()
    if not cfg.azure_blob_account_url:
        raise RuntimeError("AZURE_BLOB_ACCOUNT_URL is not configured")
    return BlobServiceClient(account_url=cfg.azure_blob_account_url, credential=_credential())


async def upload(
    container: str,
    data: bytes,
    *,
    content_type: str,
    filename: str,
) -> str:
    """Upload bytes to a container under a UUID-based key. Returns the
    blob key (NOT the full URL — callers compose URLs from container +
    key as needed).
    """
    blob_key = f"{datetime.now(timezone.utc):%Y/%m/%d}/{uuid4()}__{filename}"
    try:
        client = get_client().get_blob_client(container=container, blob=blob_key)
        await client.upload_blob(
            data,
            overwrite=False,
            content_type=content_type,
        )
        return blob_key
    except Exception as exc:
        logger.exception("nexhire.blob.upload_failed", extra={"container": container})
        raise AzureBlobError() from exc


async def generate_sas_url(
    container: str,
    blob_key: str,
    *,
    minutes_valid: int = 15,
) -> str:
    """Issue a short-lived SAS URL for a blob. Default 15 minutes.

    Used for: candidate downloads (offer letter, certificate),
    HR-facing previews, OpenSign envelope creation.
    """
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    cfg = get_settings()
    try:
        client = get_client().get_blob_client(container=container, blob=blob_key)
        # User-delegation SAS would be nicer (no shared key) but requires
        # MI; for v1 we use the account key stored in Key Vault. Slot for
        # upgrade in Phase 2.
        # Note: full implementation requires shared-key access; this is
        # the wiring shape — actual signature lands in S1 alongside the
        # document module.
        expiry = datetime.now(timezone.utc) + timedelta(minutes=minutes_valid)
        sas = generate_blob_sas(
            account_name=client.account_name,
            container_name=container,
            blob_name=blob_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            account_key=None,  # populated by S1 from Key Vault
        )
        return f"{cfg.azure_blob_account_url}/{container}/{blob_key}?{sas}"
    except Exception as exc:
        logger.exception("nexhire.blob.sas_failed")
        raise AzureBlobError() from exc
