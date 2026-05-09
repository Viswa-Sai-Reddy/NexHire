"""OpenSign REST API client.

Self-hosted OpenSign on Azure Container Instance per the spec. The
client wraps the four operations we use:
  * `create_envelope(...)` — uploads the NDA template and creates a
    signing request for the candidate.
  * `download_signed(...)` — fetches the executed PDF after a SIGNED
    webhook event (we archive it to Blob Storage).
  * `cancel_envelope(...)` — called on Day-5 auto-reject (F-17).
  * `verify_signature(headers, body)` — HMAC-SHA256 over the raw body
    using the shared secret. Reject mismatches.

Decision A8: NexHire owns reminders, so the envelope is always created
with `disable_reminders=true`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings
from app.shared.exceptions import OpenSignError, OpenSignWebhookInvalidError

logger = logging.getLogger("nexhire.opensign")


@dataclass(frozen=True, slots=True)
class EnvelopeCreateResult:
    envelope_id: str
    signing_url: str


def _client() -> httpx.AsyncClient:
    cfg = get_settings()
    if not cfg.opensign_base_url or not cfg.opensign_api_key:
        raise OpenSignError(user_message="OpenSign is not configured.")
    return httpx.AsyncClient(
        base_url=cfg.opensign_base_url,
        headers={"Authorization": f"Bearer {cfg.opensign_api_key}"},
        timeout=20.0,
    )


async def create_envelope(
    *,
    template_pdf_bytes: bytes,
    candidate_name: str,
    candidate_email: str,
    metadata: dict[str, Any],
    expiry_days: int = 5,
) -> EnvelopeCreateResult:
    cfg = get_settings()
    files = {
        "document": ("nda.pdf", template_pdf_bytes, "application/pdf"),
    }
    form: dict[str, Any] = {
        "signers": [{"name": candidate_name, "email": candidate_email}],
        "metadata": metadata,
        "expiry_days": expiry_days,
        "disable_reminders": True,
        "webhook_url": (cfg.opensign_base_url or "")
        and (cfg.frontend_base_url + "/api/v1/webhooks/opensign"),
    }
    try:
        async with _client() as client:
            response = await client.post(
                "/api/request-signature", data=form, files=files
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.exception("nexhire.opensign.create_failed")
        raise OpenSignError() from exc
    return EnvelopeCreateResult(
        envelope_id=str(payload["envelope_id"]),
        signing_url=str(payload["signing_url"]),
    )


async def download_signed(envelope_id: str) -> bytes:
    try:
        async with _client() as client:
            response = await client.get(f"/api/download/{envelope_id}")
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        logger.exception(
            "nexhire.opensign.download_failed",
            extra={"envelope_id": envelope_id},
        )
        raise OpenSignError() from exc


async def cancel_envelope(envelope_id: str) -> None:
    try:
        async with _client() as client:
            response = await client.delete(f"/api/envelopes/{envelope_id}")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        # Cancelling an already-cancelled envelope is fine; log and move on.
        logger.warning(
            "nexhire.opensign.cancel_failed",
            extra={"envelope_id": envelope_id, "error": str(exc)},
        )


def verify_signature(*, raw_body: bytes, signature_header: str) -> None:
    cfg = get_settings()
    if not cfg.opensign_webhook_signing_secret:
        raise OpenSignWebhookInvalidError(
            user_message="Webhook signing secret is not configured."
        )
    expected = hmac.new(
        cfg.opensign_webhook_signing_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    # Accept either a bare hex digest or the `sha256=<hex>` form some
    # vendors emit.
    candidate = signature_header.removeprefix("sha256=").strip()
    if not hmac.compare_digest(expected, candidate):
        raise OpenSignWebhookInvalidError()


__all__ = [
    "EnvelopeCreateResult",
    "cancel_envelope",
    "create_envelope",
    "download_signed",
    "verify_signature",
]
