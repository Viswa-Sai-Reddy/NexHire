"""OpenSign webhook handler — F-24."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.rate_limit import rate_limit
from app.modules.nda import opensign_client, service

logger = logging.getLogger("nexhire.router.opensign")

webhook_router = APIRouter(prefix="/webhooks/opensign", tags=["webhooks"])


@webhook_router.post(
    "",
    status_code=204,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="OpenSign signing-event callback (HMAC-verified).",
)
async def receive_webhook(
    request: Request,
    x_opensign_signature: str = Header(..., alias="X-OpenSign-Signature"),
    session: AsyncSession = Depends(get_session),
) -> None:
    raw = await request.body()
    opensign_client.verify_signature(
        raw_body=raw, signature_header=x_opensign_signature
    )
    payload = await request.json()

    event = str(payload.get("event") or "")
    envelope_id = str(payload.get("envelope_id") or "")
    if not envelope_id:
        return

    if event == "document_signed":
        await service.mark_signed(
            session,
            envelope_id=envelope_id,
            signed_at=_parse_ts(payload.get("signed_at")),
        )
    elif event == "document_declined":
        await service.mark_declined(
            session,
            envelope_id=envelope_id,
            declined_at=_parse_ts(payload.get("declined_at")),
        )
    elif event == "envelope_expired":
        # Day-5 job usually beats this; fall back to auto-reject path.
        await service.auto_reject_expired(session)
    else:
        logger.info(
            "nexhire.opensign.webhook_unknown_event", extra={"event": event}
        )


def _parse_ts(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
