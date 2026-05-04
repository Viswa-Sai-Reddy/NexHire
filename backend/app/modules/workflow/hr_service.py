"""HR review actions on flagged (or recalled) referrals.

Endpoints (S2.6 router) call into this module. Three actions:
  * `approve(...)` — HR_REVIEW → APPROVED. Closes the HR_REVIEW task.
  * `reject(...)`  — HR_REVIEW → HR_REJECTED (terminal, RULE-CP4 cooling).
  * `request_correction(...)` — HR_REVIEW → CORRECTION_NEEDED. Referrer
    can edit + resubmit (decision A18: edit-in-place).

Each action runs inside the caller's transaction (router uses
`get_session`); we publish audit + bus events alongside the FSM write.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.referral import cooling_period_service
from app.modules.referral.models import (
    Referral,
    ReferralStageHistory,
    Task,
)
from app.shared.constants import (
    ReferralStatus,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.shared.domain_events import (
    ReferralApproved,
    ReferralCorrectionRequested,
    ReferralHrRejected,
)
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
    InvalidStateTransitionError,
)
from app.shared.value_objects import ReferralId, UserId

logger = logging.getLogger("nexhire.workflow.hr")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _load(session: AsyncSession, referral_id: UUID) -> Referral:
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise BusinessRuleError(
            user_message="Referral not found.",
            details={"referral_id": str(referral_id)},
        )
    return referral


async def _close_review_task(
    session: AsyncSession,
    *,
    referral_id: UUID,
    hr_user_id: UUID,
    notes: str | None = None,
) -> None:
    """Close the open HR_REVIEW task for this referral (if any)."""
    task = (
        await session.execute(
            select(Task)
            .where(
                Task.referral_id == referral_id,
                Task.task_type == TaskType.HR_REVIEW.value,
                Task.status == TaskStatus.PENDING.value,
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if task is None:
        return
    task.status = TaskStatus.COMPLETED.value
    task.completed_at = _utcnow()
    task.completed_by = hr_user_id
    if notes:
        task.completion_notes = notes


# ────────────────────────────────────────────────────────────────────
# Approve.
# ────────────────────────────────────────────────────────────────────
async def approve(
    session: AsyncSession,
    *,
    referral_id: UUID,
    hr_user_id: UUID,
    hr_role: UserRole,
    notes: str | None = None,
) -> Referral:
    if hr_role not in (UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()

    referral = await _load(session, referral_id)
    if referral.status != ReferralStatus.HR_REVIEW.value:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="HR_APPROVE"
        )

    now = _utcnow()
    referral.status = ReferralStatus.APPROVED.value
    referral.current_stage = ReferralStatus.APPROVED.value
    referral.stage_entered_at = now
    referral.approved_at = now
    referral.approved_by = hr_user_id
    referral.approved_by_label = "HR"
    referral.updated_at = now

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.HR_REVIEW.value,
            to_status=ReferralStatus.APPROVED.value,
            actor_id=hr_user_id,
            actor_role=hr_role.value,
            reason=notes or "HR approved.",
        )
    )
    await _close_review_task(
        session, referral_id=referral.id, hr_user_id=hr_user_id, notes=notes
    )

    await audit.publish(
        event_type="REFERRAL_APPROVED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=hr_user_id,
        actor_role=hr_role.value,
        payload={"by_label": "HR", "notes": notes},
        session=session,
    )
    await get_bus().publish(
        ReferralApproved(
            referral_id=ReferralId(referral.id),
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
            approved_by_user_id=UserId(hr_user_id),
            approved_by_label="HR",
        )
    )

    return referral


# ────────────────────────────────────────────────────────────────────
# Reject — RULE-CP4 cooling fires here.
# ────────────────────────────────────────────────────────────────────
async def reject(
    session: AsyncSession,
    *,
    referral_id: UUID,
    hr_user_id: UUID,
    hr_role: UserRole,
    reason: str,
) -> Referral:
    if hr_role not in (UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()
    if not reason or len(reason.strip()) < 10:
        raise BusinessRuleError(
            user_message="A rejection reason of at least 10 characters is required.",
            details={"min_length": 10},
        )

    referral = await _load(session, referral_id)
    if referral.status != ReferralStatus.HR_REVIEW.value:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="HR_REJECT"
        )

    now = _utcnow()
    referral.status = ReferralStatus.HR_REJECTED.value
    referral.current_stage = ReferralStatus.HR_REJECTED.value
    referral.stage_entered_at = now
    referral.rejected_at = now
    referral.rejected_by = hr_user_id
    referral.rejection_reason = reason.strip()
    referral.updated_at = now

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.HR_REVIEW.value,
            to_status=ReferralStatus.HR_REJECTED.value,
            actor_id=hr_user_id,
            actor_role=hr_role.value,
            reason=reason.strip(),
        )
    )

    await _close_review_task(
        session,
        referral_id=referral.id,
        hr_user_id=hr_user_id,
        notes=f"Rejected: {reason[:200]}",
    )

    # RULE-CP4 — apply 3-month cooling.
    await cooling_period_service.apply(
        session,
        referral_id=referral.id,
        terminal_state=ReferralStatus.HR_REJECTED.value,
    )

    await audit.publish(
        event_type="REFERRAL_REJECTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=hr_user_id,
        actor_role=hr_role.value,
        payload={"reason": reason[:500]},
        session=session,
    )
    await get_bus().publish(
        ReferralHrRejected(
            referral_id=ReferralId(referral.id),
            rejected_by_user_id=UserId(hr_user_id),
            reason=reason[:500],
        )
    )

    return referral


# ────────────────────────────────────────────────────────────────────
# Request correction (decision A18).
# ────────────────────────────────────────────────────────────────────
async def request_correction(
    session: AsyncSession,
    *,
    referral_id: UUID,
    hr_user_id: UUID,
    hr_role: UserRole,
    notes: str,
) -> Referral:
    if hr_role not in (UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()
    if not notes or len(notes.strip()) < 10:
        raise BusinessRuleError(
            user_message="Please describe the correction needed (≥10 characters).",
        )

    referral = await _load(session, referral_id)
    if referral.status != ReferralStatus.HR_REVIEW.value:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="HR_REQUEST_CORRECTION"
        )

    now = _utcnow()
    referral.status = ReferralStatus.CORRECTION_NEEDED.value
    referral.current_stage = ReferralStatus.CORRECTION_NEEDED.value
    referral.stage_entered_at = now
    referral.updated_at = now

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.HR_REVIEW.value,
            to_status=ReferralStatus.CORRECTION_NEEDED.value,
            actor_id=hr_user_id,
            actor_role=hr_role.value,
            reason=notes.strip(),
        )
    )

    await _close_review_task(
        session,
        referral_id=referral.id,
        hr_user_id=hr_user_id,
        notes=f"Correction requested: {notes[:200]}",
    )

    await audit.publish(
        event_type="CORRECTION_REQUESTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=hr_user_id,
        actor_role=hr_role.value,
        payload={"notes": notes[:500]},
        session=session,
    )
    await get_bus().publish(
        ReferralCorrectionRequested(
            referral_id=ReferralId(referral.id),
            requested_by_user_id=UserId(hr_user_id),
            notes=notes[:500],
        )
    )

    return referral


__all__ = ["approve", "reject", "request_correction"]
