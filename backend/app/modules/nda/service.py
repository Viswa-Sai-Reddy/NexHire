"""NDA lifecycle service (RULE-N1..N4 + F-16, F-17, F-24).

Operations:
  * `issue_for_intern(intern_id)` — creates the OpenSign envelope, NDA
    record, and the candidate-facing signing email. Triggered by
    `JoiningFormLocked` (after F-34 auto-generates the Non-Worker ID).
  * `mark_signed(envelope_id, signed_at, signed_pdf)` — webhook path.
  * `mark_declined(envelope_id, declined_at)` — webhook path. RULE-N4
    immediate terminal rejection + cooling.
  * `auto_reject_expired(...)` — APScheduler entry. Day-5 timeout +
    cooling.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.nda import opensign_client
from app.modules.nda.models import NdaRecord
from app.modules.onboarding.models import Intern
from app.modules.referral import cooling_period_service
from app.modules.referral.models import (
    Referral,
    ReferralStageHistory,
)
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    NDA_DEADLINE_DAYS,
    NdaStatus,
    ReferralStatus,
)
from app.shared.domain_events import DomainEvent
from dataclasses import dataclass

logger = logging.getLogger("nexhire.nda.service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────────
# Domain events emitted by this module.
# ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class NdaIssued(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    envelope_id: str
    signing_url: str
    candidate_email: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NdaSigned(DomainEvent):
    intern_id: UUID
    referral_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class NdaDeclined(DomainEvent):
    intern_id: UUID
    referral_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class NdaAutoRejected(DomainEvent):
    intern_id: UUID
    referral_id: UUID


# ────────────────────────────────────────────────────────────────────
# Issue.
# ────────────────────────────────────────────────────────────────────
async def issue_for_intern(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> NdaRecord:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    record = (
        await session.execute(
            select(NdaRecord).where(NdaRecord.intern_id == intern_id)
        )
    ).scalar_one_or_none()
    if record is None:
        record = NdaRecord(intern_id=intern_id, status=NdaStatus.PENDING.value)
        session.add(record)
        await session.flush()

    if record.status not in (NdaStatus.PENDING.value, NdaStatus.SENT.value):
        # Already signed/declined/expired — nothing to do.
        return record

    cfg = get_settings()
    if not cfg.opensign_base_url:
        # Dev shortcut: pretend an envelope was created so downstream
        # FSM transitions still flow. Real OpenSign integration takes
        # over the moment credentials are configured.
        envelope_id = f"dev-env-{intern_id}"
        signing_url = "about:blank"
    else:
        # Real path. The template PDF lookup lives in the Document
        # Storage S5 expansion; for now we ship a tiny placeholder.
        result = await opensign_client.create_envelope(
            template_pdf_bytes=_dev_pdf_placeholder(),
            candidate_name=referral.candidate_name,
            candidate_email=referral.candidate_email,
            metadata={
                "referral_id": str(referral.id),
                "intern_id": str(intern.id),
            },
            expiry_days=NDA_DEADLINE_DAYS,
        )
        envelope_id = result.envelope_id
        signing_url = result.signing_url

    record.opensign_envelope_id = envelope_id
    record.template_version = "v1"
    record.status = NdaStatus.SENT.value
    record.issued_at = _utcnow()
    record.sent_at = _utcnow()

    referral.status = ReferralStatus.NDA_PENDING.value
    referral.current_stage = ReferralStatus.NDA_PENDING.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.ID_ISSUED.value,
            to_status=ReferralStatus.NDA_PENDING.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason="NDA envelope created.",
        )
    )

    await audit.publish(
        event_type="NDA_ISSUED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "envelope_id": envelope_id,
            "referral_id": str(referral.id),
        },
        session=session,
    )
    await get_bus().publish(
        NdaIssued(
            intern_id=intern.id,
            referral_id=referral.id,
            envelope_id=envelope_id,
            signing_url=signing_url,
            candidate_email=referral.candidate_email,
        )
    )
    return record


def _dev_pdf_placeholder() -> bytes:
    """Tiny valid PDF — real template upload from Blob lands in S5."""
    return (
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )


# ────────────────────────────────────────────────────────────────────
# Signing event paths.
# ────────────────────────────────────────────────────────────────────
async def mark_signed(
    session: AsyncSession,
    *,
    envelope_id: str,
    signed_at: datetime,
    signed_pdf: bytes | None = None,
) -> NdaRecord:
    record = await _by_envelope(session, envelope_id)
    if record.status == NdaStatus.SIGNED.value:
        return record  # idempotent

    referral = await _referral_for(session, record)

    record.status = NdaStatus.SIGNED.value
    record.signed_at = signed_at

    referral.status = ReferralStatus.NDA_SIGNED.value
    referral.current_stage = ReferralStatus.NDA_SIGNED.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.NDA_PENDING.value,
            to_status=ReferralStatus.NDA_SIGNED.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason="NDA signed by candidate.",
        )
    )

    await audit.publish(
        event_type="NDA_SIGNED",
        entity_type="INTERN",
        entity_id=record.intern_id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={"envelope_id": envelope_id, "signed_at": signed_at.isoformat()},
        session=session,
    )
    await get_bus().publish(
        NdaSigned(intern_id=record.intern_id, referral_id=referral.id)
    )
    _ = signed_pdf  # archived to Blob in S5 alongside the doc module
    return record


async def mark_declined(
    session: AsyncSession,
    *,
    envelope_id: str,
    declined_at: datetime,
) -> NdaRecord:
    record = await _by_envelope(session, envelope_id)
    if record.status == NdaStatus.DECLINED.value:
        return record

    referral = await _referral_for(session, record)
    record.status = NdaStatus.DECLINED.value
    record.declined_at = declined_at

    referral.status = ReferralStatus.NDA_DECLINED_REJECTED.value
    referral.current_stage = ReferralStatus.NDA_DECLINED_REJECTED.value
    referral.stage_entered_at = _utcnow()
    referral.rejected_at = _utcnow()
    referral.rejection_reason = "NDA_DECLINED"
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.NDA_PENDING.value,
            to_status=ReferralStatus.NDA_DECLINED_REJECTED.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason="Candidate declined the NDA.",
        )
    )

    # RULE-N4 + RULE-CP1 — 6-month cooling.
    await cooling_period_service.apply(
        session,
        referral_id=referral.id,
        terminal_state=ReferralStatus.NDA_DECLINED_REJECTED.value,
    )

    await audit.publish(
        event_type="NDA_DECLINED",
        entity_type="INTERN",
        entity_id=record.intern_id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={"envelope_id": envelope_id},
        session=session,
    )
    await get_bus().publish(
        NdaDeclined(intern_id=record.intern_id, referral_id=referral.id)
    )
    return record


# ────────────────────────────────────────────────────────────────────
# Day-5 timeout (APScheduler).
# ────────────────────────────────────────────────────────────────────
async def auto_reject_expired(session: AsyncSession) -> int:
    cutoff = _utcnow() - timedelta(days=NDA_DEADLINE_DAYS)
    rows = (
        await session.execute(
            select(NdaRecord).where(
                NdaRecord.status == NdaStatus.SENT.value,
                NdaRecord.sent_at.is_not(None),
                NdaRecord.sent_at <= cutoff,
            )
        )
    ).scalars().all()
    handled = 0
    for record in rows:
        referral = await _referral_for(session, record)
        if referral.status not in (
            ReferralStatus.NDA_PENDING.value,
            ReferralStatus.NDA_SIGNED.value,  # idempotency guard
        ):
            continue

        record.status = NdaStatus.EXPIRED.value
        record.expired_at = _utcnow()
        record.auto_rejected_at = _utcnow()

        referral.status = ReferralStatus.NDA_TIMEOUT_REJECTED.value
        referral.current_stage = ReferralStatus.NDA_TIMEOUT_REJECTED.value
        referral.stage_entered_at = _utcnow()
        referral.rejected_at = _utcnow()
        referral.rejection_reason = "NDA_AUTO_REJECTED"
        referral.updated_at = _utcnow()

        session.add(
            ReferralStageHistory(
                referral_id=referral.id,
                from_status=ReferralStatus.NDA_PENDING.value,
                to_status=ReferralStatus.NDA_TIMEOUT_REJECTED.value,
                actor_id=AI_SYSTEM_USER_ID,
                actor_role="SYSTEM",
                reason="Day-5 NDA auto-rejection.",
            )
        )

        # Best-effort cancel on OpenSign side.
        if record.opensign_envelope_id:
            await opensign_client.cancel_envelope(record.opensign_envelope_id)

        # 3-month cooling (RULE-CP3).
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.NDA_TIMEOUT_REJECTED.value,
        )

        await audit.publish(
            event_type="NDA_AUTO_REJECTED",
            entity_type="INTERN",
            entity_id=record.intern_id,
            actor_user_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            payload={"envelope_id": record.opensign_envelope_id},
            session=session,
        )
        await get_bus().publish(
            NdaAutoRejected(intern_id=record.intern_id, referral_id=referral.id)
        )
        handled += 1
    return handled


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
async def _by_envelope(
    session: AsyncSession, envelope_id: str
) -> NdaRecord:
    record = (
        await session.execute(
            select(NdaRecord).where(
                NdaRecord.opensign_envelope_id == envelope_id
            )
        )
    ).scalar_one_or_none()
    if record is None:
        from app.shared.exceptions import BusinessRuleError

        raise BusinessRuleError(
            user_message="NDA envelope not recognized.",
            details={"envelope_id": envelope_id},
        )
    return record


async def _referral_for(session: AsyncSession, record: NdaRecord) -> Referral:
    return (
        await session.execute(
            select(Referral)
            .join(Intern, Intern.referral_id == Referral.id)
            .where(Intern.id == record.intern_id)
        )
    ).scalar_one()


__all__ = [
    "NdaAutoRejected",
    "NdaDeclined",
    "NdaIssued",
    "NdaSigned",
    "auto_reject_expired",
    "issue_for_intern",
    "mark_declined",
    "mark_signed",
]
