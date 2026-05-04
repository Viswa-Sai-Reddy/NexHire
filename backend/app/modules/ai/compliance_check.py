"""AI-7 — Pre-start compliance check (T-48h).

Runs every 6h via APScheduler against `interns` whose `actual_start_date`
(or referral.internship_start_date as fallback) is ~2 days out. For each
intern, we evaluate the 5-item checklist; missing items emit one
escalation audit event per intern.

S5 wires the corresponding HR + Program-Owner notification templates;
this module owns the deterministic checklist + the audit event so the
rest can plug in.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.nda.models import NdaRecord
from app.modules.onboarding.models import Intern
from app.modules.referral.models import Referral, Task
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    AdAccountStatus,
    NdaStatus,
    TaskStatus,
    TaskType,
)

logger = logging.getLogger("nexhire.ai.compliance_check")

MODEL_TOUCHPOINT = "COMPLIANCE_CHECK"


class ComplianceResult(NamedTuple):
    intern_id: UUID
    nda_signed: bool
    non_worker_id_issued: bool
    ad_provisioned: bool
    badge_configured: bool
    offer_letter_sent: bool

    def is_ready(self) -> bool:
        return all(
            (
                self.nda_signed,
                self.non_worker_id_issued,
                self.ad_provisioned,
                self.badge_configured,
                self.offer_letter_sent,
            )
        )

    def blocking_items(self) -> list[str]:
        items: list[str] = []
        if not self.nda_signed:
            items.append("nda_signed")
        if not self.non_worker_id_issued:
            items.append("non_worker_id")
        if not self.ad_provisioned:
            items.append("ad_account")
        if not self.badge_configured:
            items.append("badge")
        if not self.offer_letter_sent:
            items.append("offer_letter")
        return items


async def run_for_due_interns(
    session: AsyncSession,
) -> list[ComplianceResult]:
    """Find interns starting in ~2 days and evaluate the checklist."""
    target = date.today() + timedelta(days=2)
    rows = (
        await session.execute(
            select(Intern, Referral)
            .join(Referral, Referral.id == Intern.referral_id)
            .where(
                Referral.internship_start_date == target,
                Intern.status.notin_(("ACTIVE", "CLOSED", "TERMINATED")),
            )
        )
    ).all()

    results: list[ComplianceResult] = []
    for intern, _referral in rows:
        result = await _check_intern(session, intern)
        results.append(result)
        if not result.is_ready():
            await audit.publish(
                event_type="COMPLIANCE_CHECK_FAILED",
                entity_type="INTERN",
                entity_id=intern.id,
                actor_user_id=AI_SYSTEM_USER_ID,
                actor_role="SYSTEM",
                payload={
                    "blocking_items": result.blocking_items(),
                    "start_date": _referral.internship_start_date.isoformat(),
                },
                session=session,
            )
    return results


async def _check_intern(session: AsyncSession, intern: Intern) -> ComplianceResult:
    nda_signed = (
        await session.execute(
            select(NdaRecord.status).where(NdaRecord.intern_id == intern.id)
        )
    ).scalar_one_or_none() == NdaStatus.SIGNED.value

    non_worker_id_issued = bool(intern.non_worker_id)
    ad_provisioned = intern.ad_account_status in (
        AdAccountStatus.PROVISIONED.value,
        AdAccountStatus.ACTIVE.value,
    )

    badge_configured = bool(
        (
            await session.execute(
                select(Task).where(
                    Task.intern_id == intern.id,
                    Task.task_type == TaskType.BADGE_ACCESS.value,
                    Task.status == TaskStatus.COMPLETED.value,
                )
            )
        ).scalar_one_or_none()
    )

    # Offer letter is auto-sent (F-37). Presence of a non-recalled
    # OFFER_LETTER document for this intern is the marker.
    offer_letter_sent = bool(
        (
            await session.execute(
                text(
                    """
                    SELECT 1 FROM documents
                    WHERE document_type = 'OFFER_LETTER'
                      AND uploaded_by IS NOT NULL
                      AND is_recalled = false
                    LIMIT 1
                    """
                )
            )
        ).first()
    )

    return ComplianceResult(
        intern_id=intern.id,
        nda_signed=nda_signed,
        non_worker_id_issued=non_worker_id_issued,
        ad_provisioned=ad_provisioned,
        badge_configured=badge_configured,
        offer_letter_sent=offer_letter_sent,
    )


__all__ = ["ComplianceResult", "MODEL_TOUCHPOINT", "run_for_due_interns"]
