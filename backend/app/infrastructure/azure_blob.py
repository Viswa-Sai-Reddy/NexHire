"""Azure Blob Storage client wrapper.

S0 ships a minimal singleton + the shape of upload + SAS generation that
the rest of the codebase expects. S1 fleshes out the upload pipeline
(virus scan via Azure Defender, deterministic key generation, retention
policy hooks).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import uuid4

from app.config import get_settings
from app.shared.exceptions import AzureBlobError

if TYPE_CHECKING:
    from azure.core.credentials_async import AsyncTokenCredential
    from azure.storage.blob.aio import BlobServiceClient

logger = logging.getLogger("nexhire.blob")


@lru_cache(maxsize=1)
def _credential() -> AsyncTokenCredential:
    from azure.identity.aio import DefaultAzureCredential

    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_client() -> BlobServiceClient:
    from azure.storage.blob.aio import BlobServiceClient

    cfg = get_settings()
    if not cfg.azure_blob_account_url:
        raise RuntimeError("AZURE_BLOB_ACCOUNT_URL is not configured")
    # Shared-key auth when the account key is present (works without
    # `az login` / Managed Identity). Otherwise fall back to AAD.
    credential: object = cfg.azure_blob_account_key or _credential()
    return BlobServiceClient(account_url=cfg.azure_blob_account_url, credential=credential)


async def upload(
    container: str,
    data: bytes,
    *,
    content_type: str,
    filename: str,
    blob_key: str | None = None,
    overwrite: bool = False,
) -> str:
    """Upload bytes to a container. Returns the blob key (NOT the full
    URL — callers compose URLs from container + key as needed).

    If `blob_key` is provided, the data is stored at that exact key —
    useful when callers (e.g. the certificate generator) need a
    deterministic, lookup-friendly path. Otherwise a UUID-based key is
    auto-generated.
    """
    if blob_key is None:
        blob_key = f"{datetime.now(UTC):%Y/%m/%d}/{uuid4()}__{filename}"
    try:
        client = get_client().get_blob_client(container=container, blob=blob_key)
        await client.upload_blob(
            data,
            overwrite=overwrite,
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
    if not cfg.azure_blob_account_key:
        raise AzureBlobError(
            "SAS generation needs AZURE_BLOB_ACCOUNT_KEY (shared key). "
            "User-delegation SAS via Managed Identity is a Phase-2 upgrade."
        )
    try:
        client = get_client().get_blob_client(container=container, blob=blob_key)
        expiry = datetime.now(UTC) + timedelta(minutes=minutes_valid)
        if not client.account_name:
            raise AzureBlobError()
        sas = generate_blob_sas(
            account_name=client.account_name,
            container_name=container,
            blob_name=blob_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            account_key=cfg.azure_blob_account_key,
        )
        return f"{cfg.azure_blob_account_url}/{container}/{blob_key}?{sas}"
    except Exception as exc:
        logger.exception("nexhire.blob.sas_failed")
        raise AzureBlobError() from exc
