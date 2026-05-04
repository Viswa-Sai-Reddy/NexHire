"""Internship lifecycle service (Blueprint §4.1 phases 6 + 7).

Operations:
  * `confirm_start(intern_id, mentor_user_id)` — ACCESS_PENDING → ACTIVE.
    Mentor confirms the intern arrived; AD account is enabled; FSM
    advances.
  * `request_extension(...)` — A16 caps: max 2 extensions, ≤4 weeks each.
  * `confirm_completion(...)` — ACTIVE → CLOSURE_PENDING. Mentor records
    structured closure feedback (decision A19).
  * `terminate(...)` — A20: candidate / HR / mentor can each initiate.
    Triggers RULE-CP2 (TERMINATED) cooling.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.access import graph_client
from app.modules.onboarding.models import Intern
from app.modules.referral import cooling_period_service
from app.modules.referral.models import (
    Referral,
    ReferralStageHistory,
)
from app.shared.constants import (
    AdAccountStatus,
    EXTENSION_MAX_COUNT,
    EXTENSION_MAX_DAYS,
    InternStatus,
    ReferralStatus,
    UserRole,
)
from app.shared.domain_events import DomainEvent
from app.shared.exceptions import (
    BusinessRuleError,
    ExtensionAfterEndDateError,
    ExtensionLimitReachedError,
    InsufficientPermissionsError,
    InternshipNotActiveError,
    InvalidExtensionDurationError,
    InvalidStateTransitionError,
)
from dataclasses import dataclass

logger = logging.getLogger("nexhire.lifecycle.service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────────
# Domain events emitted by this module.
# ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class InternshipStarted(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    actual_start_date: date


@dataclass(frozen=True, slots=True, kw_only=True)
class InternshipExtended(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    new_end_date: date
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ClosurePending(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    closure_feedback: dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class InternshipTerminated(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    initiated_by_user_id: UUID
    initiated_by_role: str
    reason: str


# ────────────────────────────────────────────────────────────────────
# Confirm start.
# ────────────────────────────────────────────────────────────────────
async def confirm_start(
    session: AsyncSession,
    *,
    intern_id: UUID,
    mentor_user_id: UUID,
    today: date | None = None,
) -> Intern:
    today = today or date.today()
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    if referral.mentor_id != mentor_user_id:
        raise InsufficientPermissionsError(
            user_message="Only the assigned mentor can confirm the start."
        )
    if referral.status != ReferralStatus.ACCESS_PENDING.value:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="CONFIRM_START"
        )

    # Enable AD account if it's been provisioned.
    if (
        intern.ad_account_status == AdAccountStatus.PROVISIONED.value
        and intern.ad_account_username
    ):
        try:
            await graph_client.set_account_enabled(
                aad_object_id=intern.ad_account_username, enabled=True
            )
        except Exception:  # noqa: BLE001 — graph errors don't block start
            logger.warning("nexhire.lifecycle.ad_enable_failed")

    intern.actual_start_date = today
    intern.status = InternStatus.ACTIVE.value
    intern.ad_account_status = AdAccountStatus.ACTIVE.value
    intern.updated_at = _utcnow()

    referral.status = ReferralStatus.ACTIVE.value
    referral.current_stage = ReferralStatus.ACTIVE.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.ACCESS_PENDING.value,
            to_status=ReferralStatus.ACTIVE.value,
            actor_id=mentor_user_id,
            actor_role="MENTOR",
            reason="Intern started — confirmed by mentor.",
        )
    )

    await audit.publish(
        event_type="INTERNSHIP_STARTED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=mentor_user_id,
        actor_role="MENTOR",
        payload={"start_date": today.isoformat()},
        session=session,
    )
    await get_bus().publish(
        InternshipStarted(
            intern_id=intern.id,
            referral_id=referral.id,
            actual_start_date=today,
        )
    )
    return intern


# ────────────────────────────────────────────────────────────────────
# Extension.
# ────────────────────────────────────────────────────────────────────
async def request_extension(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: UUID,
    actor_role: UserRole,
    new_end_date: date,
    reason: str,
) -> Intern:
    if actor_role not in (UserRole.MENTOR, UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()
    if not reason or len(reason.strip()) < 10:
        raise BusinessRuleError(
            user_message="Extension reason must be at least 10 characters."
        )

    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    if referral.status not in (
        ReferralStatus.ACTIVE.value,
        ReferralStatus.EXTENDED.value,
    ):
        raise InternshipNotActiveError()
    current_end = intern.actual_end_date or referral.internship_end_date
    if current_end is None or new_end_date <= current_end:
        raise InvalidExtensionDurationError(
            user_message="The new end date must be after the current end date."
        )
    if (new_end_date - current_end).days > EXTENSION_MAX_DAYS:
        raise InvalidExtensionDurationError()
    if intern.extension_count >= EXTENSION_MAX_COUNT:
        raise ExtensionLimitReachedError()
    if date.today() > current_end:
        raise ExtensionAfterEndDateError()

    intern.actual_end_date = new_end_date
    intern.extension_count += 1
    intern.status = InternStatus.EXTENDED.value
    intern.updated_at = _utcnow()

    referral.status = ReferralStatus.EXTENDED.value
    referral.current_stage = ReferralStatus.EXTENDED.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.ACTIVE.value,
            to_status=ReferralStatus.EXTENDED.value,
            actor_id=actor_user_id,
            actor_role=actor_role.value,
            reason=reason[:500],
        )
    )

    await audit.publish(
        event_type="INTERNSHIP_EXTENDED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={
            "new_end_date": new_end_date.isoformat(),
            "extension_number": intern.extension_count,
        },
        session=session,
    )
    await get_bus().publish(
        InternshipExtended(
            intern_id=intern.id,
            referral_id=referral.id,
            new_end_date=new_end_date,
            reason=reason[:500],
        )
    )
    return intern


# ────────────────────────────────────────────────────────────────────
# Confirm completion (mentor; structured feedback per A19).
# ────────────────────────────────────────────────────────────────────
async def confirm_completion(
    session: AsyncSession,
    *,
    intern_id: UUID,
    mentor_user_id: UUID,
    feedback: dict[str, Any],
) -> Intern:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()
    if referral.mentor_id != mentor_user_id:
        raise InsufficientPermissionsError()
    if referral.status not in (
        ReferralStatus.ACTIVE.value,
        ReferralStatus.EXTENDED.value,
    ):
        raise InternshipNotActiveError()

    # Validate the structured shape (A19).
    required = (
        "project_summary",
        "skills_demonstrated",
        "recommendation_strength",
    )
    for key in required:
        if key not in feedback:
            raise BusinessRuleError(
                user_message=f"Missing closure feedback field: {key}",
            )
    score = feedback.get("recommendation_strength")
    if not isinstance(score, int) or not (1 <= score <= 5):
        raise BusinessRuleError(
            user_message="recommendation_strength must be an integer 1–5."
        )

    intern.mentor_closure_feedback = feedback
    intern.mentor_confirmed_completion = True
    intern.actual_end_date = intern.actual_end_date or date.today()
    intern.status = InternStatus.CLOSURE_PENDING.value
    intern.updated_at = _utcnow()

    referral.status = ReferralStatus.CLOSURE_PENDING.value
    referral.current_stage = ReferralStatus.CLOSURE_PENDING.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=referral.status,
            to_status=ReferralStatus.CLOSURE_PENDING.value,
            actor_id=mentor_user_id,
            actor_role="MENTOR",
            reason="Mentor confirmed completion.",
            payload={"feedback_summary": feedback.get("project_summary", "")[:200]},
        )
    )

    await audit.publish(
        event_type="INTERNSHIP_CLOSURE_PENDING",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=mentor_user_id,
        actor_role="MENTOR",
        payload={"recommendation_strength": score},
        session=session,
    )
    await get_bus().publish(
        ClosurePending(
            intern_id=intern.id,
            referral_id=referral.id,
            closure_feedback=feedback,
        )
    )

    # Disable AD account at closure (deactivation per F-22).
    if intern.ad_account_username:
        try:
            await graph_client.set_account_enabled(
                aad_object_id=intern.ad_account_username, enabled=False
            )
            intern.ad_account_status = AdAccountStatus.DISABLED.value
        except Exception:  # noqa: BLE001
            logger.warning("nexhire.lifecycle.ad_disable_failed")

    return intern


# ────────────────────────────────────────────────────────────────────
# Termination — decision A20: candidate, HR, or mentor.
# ────────────────────────────────────────────────────────────────────
async def terminate(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: UUID,
    actor_role: UserRole,
    reason: str,
) -> Intern:
    if actor_role not in (UserRole.CANDIDATE, UserRole.HR, UserRole.MENTOR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()
    if not reason or len(reason.strip()) < 10:
        raise BusinessRuleError(
            user_message="Termination reason must be at least 10 characters."
        )

    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()
    if referral.status not in (
        ReferralStatus.ACTIVE.value,
        ReferralStatus.EXTENDED.value,
    ):
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="TERMINATE"
        )

    intern.status = InternStatus.TERMINATED.value
    intern.actual_end_date = intern.actual_end_date or date.today()
    intern.updated_at = _utcnow()

    referral.status = ReferralStatus.TERMINATED.value
    referral.current_stage = ReferralStatus.TERMINATED.value
    referral.stage_entered_at = _utcnow()
    referral.rejected_at = _utcnow()
    referral.rejection_reason = "TERMINATED: " + reason[:200]
    referral.updated_at = _utcnow()

    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=referral.status,
            to_status=ReferralStatus.TERMINATED.value,
            actor_id=actor_user_id,
            actor_role=actor_role.value,
            reason=reason[:500],
        )
    )

    # RULE-CP2 — 6-month cooling on TERMINATED.
    await cooling_period_service.apply(
        session,
        referral_id=referral.id,
        terminal_state=ReferralStatus.TERMINATED.value,
    )

    await audit.publish(
        event_type="INTERNSHIP_TERMINATED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={"reason": reason[:500]},
        session=session,
    )
    await get_bus().publish(
        InternshipTerminated(
            intern_id=intern.id,
            referral_id=referral.id,
            initiated_by_user_id=actor_user_id,
            initiated_by_role=actor_role.value,
            reason=reason[:500],
        )
    )

    # Disable AD account.
    if intern.ad_account_username:
        try:
            await graph_client.set_account_enabled(
                aad_object_id=intern.ad_account_username, enabled=False
            )
            intern.ad_account_status = AdAccountStatus.DISABLED.value
        except Exception:  # noqa: BLE001
            logger.warning("nexhire.lifecycle.ad_disable_failed")

    return intern


__all__ = [
    "ClosurePending",
    "InternshipExtended",
    "InternshipStarted",
    "InternshipTerminated",
    "confirm_completion",
    "confirm_start",
    "request_extension",
    "terminate",
]
