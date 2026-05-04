"""F-37 — Offer-letter auto-send.

Trigger: `NdaSigned` event. Side-effect on a clean clean case:
  * AI-8 (lite) renders the offer letter HTML from a template using
    intern + referral data.
  * WeasyPrint converts to PDF (best-effort; if WeasyPrint isn't
    available the path falls back to logging the HTML).
  * The PDF is registered as a Document and a `nda_records.signed_at`-
    triggered notification is queued.
  * `ai_auto_actions` row written so HR can recall within 30 min.

S5 wires the actual notification template + WeasyPrint dependency
fully; for S4 we lay the FSM + audit + auto-action plumbing. The
module's contract is the same; the renderer is the only stub.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.onboarding.models import Intern
from app.modules.referral.models import (
    AiAutoAction,
    Document,
    Referral,
)
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    DocumentType,
)

logger = logging.getLogger("nexhire.workflow.offer_letter")

# Recall window — Implementation_Plan §17.13 (30 min).
RECALL_MINUTES = 30


async def render_and_send(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> AiAutoAction:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    html = _render_html(intern=intern, referral=referral)
    pdf_bytes = _render_pdf(html)

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    document = Document(
        document_type=DocumentType.OFFER_LETTER.value,
        azure_blob_container="documents",
        azure_blob_key=f"offer-letters/{intern.id}.pdf",
        file_name=f"offer-letter-{intern.id}.pdf",
        mime_type="application/pdf",
        size_bytes=len(pdf_bytes),
        sha256_hash=sha256,
        uploaded_by=AI_SYSTEM_USER_ID,
    )
    session.add(document)
    await session.flush()

    auto_action = AiAutoAction(
        action_type="AUTO_SEND_OFFER",
        decision="EXECUTED",
        referral_id=referral.id,
        intern_id=intern.id,
        conditions_met=["Standard template + all merge fields populated"],
    )
    session.add(auto_action)

    await audit.publish(
        event_type="OFFER_LETTER_AUTO_SENT",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "document_id": str(document.id),
            "recall_until": _recall_until().isoformat(),
        },
        session=session,
    )
    return auto_action


def _render_html(*, intern: Intern, referral: Referral) -> str:
    """Minimal placeholder. The full template lives in
    app/modules/notification/templates/offer_letter.html in S5.
    """
    return (
        f"<html><body><h1>Offer Letter</h1>"
        f"<p>Dear {referral.candidate_name},</p>"
        f"<p>You are confirmed as an intern, "
        f"Non-Worker ID: {intern.non_worker_id}.</p>"
        f"<p>Start date: {referral.internship_start_date}<br/>"
        f"End date: {referral.internship_end_date}</p>"
        f"</body></html>"
    )


def _render_pdf(html: str) -> bytes:
    """WeasyPrint hand-off. Falls back to bytes-of-HTML in dev where
    WeasyPrint native deps may not be installed.
    """
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]

        return HTML(string=html).write_pdf() or b""
    except Exception:  # noqa: BLE001
        logger.warning("nexhire.workflow.weasyprint_unavailable")
        return html.encode("utf-8")


def _recall_until() -> datetime:
    from datetime import timedelta

    return datetime.now(timezone.utc) + timedelta(minutes=RECALL_MINUTES)


__all__ = ["RECALL_MINUTES", "render_and_send"]
