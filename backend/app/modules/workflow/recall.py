"""Recall service for AI auto-actions (decision §17.13 + Blueprint §18.6).

S2 covers AUTO_APPROVE recall. Other auto-action types (AUTO_LOCK,
AUTO_SEND_OFFER, AUTO_SEND_CERT) ship in their respective slices but
all use this same module — the recall window + compensating-action
shape is identical, only the side-effect details vary.

Behaviour:
  * Window check — `executed_at + RECALL_HOURS[action_type] >= NOW()`.
    After the window expires the button is hidden by the UI; if a
    forged request arrives we still re-check here and reject.
  * Mark `ai_auto_actions.recalled_*` columns.
  * Reverse the FSM transition (AUTO_APPROVE: APPROVED → HR_REVIEW
    via the auto-router so a human picks it up).
  * Audit + emit `AutoApprovalRecalled`.

Compensating notifications (e.g. "please disregard the offer letter")
are wired in S5 when those notifications actually exist. Until then,
recall is a clean state-revert.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.ai import auto_router
from app.modules.referral.models import (
    AiAutoAction,
    Referral,
    ReferralStageHistory,
)
from app.modules.workflow.auto_approval import AUTO_APPROVE_RECALL_HOURS
from app.shared.constants import (
    ReferralStatus,
    TaskType,
    UserRole,
)
from app.shared.domain_events import AutoApprovalRecalled
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
    InvalidStateTransitionError,
)
from app.shared.value_objects import ReferralId, UserId

logger = logging.getLogger("nexhire.workflow.recall")


# Window per auto-action type. Spec §18.6:
#   AUTO_APPROVE   → 2h
#   AUTO_LOCK      → 1h    (S3 — joining-form auto-lock)
#   AUTO_SEND_OFFER → 30m  (S5 — offer letter)
#   AUTO_SEND_CERT  → 48h  (S5 — certificate)
RECALL_HOURS: Mapping[str, int] = {
    "AUTO_APPROVE": AUTO_APPROVE_RECALL_HOURS,
    "AUTO_LOCK": 1,
    "AUTO_SEND_OFFER": 0,  # 30m — handled per-minute in router; placeholder
    "AUTO_SEND_CERT": 48,
}


class RecallWindowExpiredError(BusinessRuleError):
    code = "RECALL_WINDOW_EXPIRED"
    rule_id = "F-35"
    user_message = "The recall window for this AI action has closed."


class AlreadyRecalledError(BusinessRuleError):
    code = "ALREADY_RECALLED"
    rule_id = "F-35"
    user_message = "This AI action has already been recalled."


# ────────────────────────────────────────────────────────────────────
# Public entry — recall an AUTO_APPROVE.
# ────────────────────────────────────────────────────────────────────
async def recall_auto_approve(
    session: AsyncSession,
    *,
    referral_id: UUID,
    hr_user_id: UUID,
    hr_role: UserRole,
    reason: str | None = None,
) -> Referral:
    """HR clicks "Recall" within the 2h window. Status reverts to
    HR_REVIEW with a fresh HR-review task.
    """
    if hr_role not in (UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError(
            user_message="Only HR can recall an auto-approval."
        )

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise BusinessRuleError(
            user_message="Referral not found.",
            details={"referral_id": str(referral_id)},
        )

    if referral.status != ReferralStatus.APPROVED.value:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="RECALL_AUTO_APPROVE"
        )
    if referral.approved_by_label != "AI_AUTO_APPROVAL":
        raise InvalidStateTransitionError(
            current_status="APPROVED_BY_HUMAN",
            attempted_action="RECALL_AUTO_APPROVE",
        )

    auto_action = (
        await session.execute(
            select(AiAutoAction)
            .where(
                AiAutoAction.referral_id == referral_id,
                AiAutoAction.action_type == "AUTO_APPROVE",
                AiAutoAction.decision == "EXECUTED",
            )
            .order_by(AiAutoAction.executed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if auto_action is None:
        raise InvalidStateTransitionError(
            current_status="NO_AUTO_ACTION_RECORD",
            attempted_action="RECALL_AUTO_APPROVE",
        )
    if auto_action.recalled_at is not None:
        raise AlreadyRecalledError()

    now = datetime.now(UTC)
    window_end = auto_action.executed_at + timedelta(
        hours=RECALL_HOURS["AUTO_APPROVE"]
    )
    if now > window_end:
        raise RecallWindowExpiredError()

    # ── Mutate ──
    auto_action.recalled_at = now
    auto_action.recalled_by = hr_user_id
    auto_action.recall_reason = reason

    referral.status = ReferralStatus.HR_REVIEW.value
    referral.current_stage = ReferralStatus.HR_REVIEW.value
    referral.stage_entered_at = now
    referral.approved_at = None
    referral.approved_by = None
    referral.approved_by_label = None
    referral.updated_at = now

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.APPROVED.value,
            to_status=ReferralStatus.HR_REVIEW.value,
            actor_id=hr_user_id,
            actor_role=hr_role.value,
            reason=f"Auto-approval recalled: {reason or 'no reason given'}",
        )
    )

    # Re-route an HR_REVIEW task to whoever's least loaded.
    sla = now + timedelta(hours=48)
    await auto_router.create_routed_task(
        session,
        task_type=TaskType.HR_REVIEW,
        role=UserRole.HR,
        sla_deadline=sla,
        referral_id=referral.id,
    )

    await audit.publish(
        event_type="REFERRAL_AUTO_APPROVAL_RECALLED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=hr_user_id,
        actor_role=hr_role.value,
        payload={
            "auto_action_id": str(auto_action.id),
            "recall_reason": reason,
            "recalled_within_seconds": int((now - auto_action.executed_at).total_seconds()),
        },
        session=session,
    )

    await get_bus().publish(
        AutoApprovalRecalled(
            referral_id=ReferralId(referral.id),
            recalled_by_user_id=UserId(hr_user_id),
            recall_reason=reason,
        )
    )

    return referral


__all__ = [
    "RECALL_HOURS",
    "AlreadyRecalledError",
    "RecallWindowExpiredError",
    "recall_auto_approve",
]
