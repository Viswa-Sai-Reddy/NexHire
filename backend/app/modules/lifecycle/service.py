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
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
    EXTENSION_MAX_COUNT,
    EXTENSION_MAX_DAYS,
    TERMINAL_REFERRAL_STATUSES,
    AdAccountStatus,
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

logger = logging.getLogger("nexhire.lifecycle.service")


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
class InternshipClosed(DomainEvent):
    """Final terminal-CLOSED state. Emitted after AI-8 auto-sends the
    certificate. Notification module subscribes to email the candidate
    with their certificate.
    """

    intern_id: UUID
    referral_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class InternshipTerminated(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    initiated_by_user_id: UUID
    initiated_by_role: str
    reason: str


# ────────────────────────────────────────────────────────────────────
# List the mentor's interns (S18 workspace).
# ────────────────────────────────────────────────────────────────────
async def list_for_mentor(
    session: AsyncSession,
    *,
    mentor_user_id: UUID,
) -> list[tuple[Intern | None, Referral, int | None, list[str]]]:
    """Return every referral the mentor is assigned to, including ones
    that haven't yet reached the APPROVED stage (no Intern row yet),
    plus the AI-3 risk score and AI-1 red flags so the dashboard can
    show context next to the Accept/Reject buttons.

    Each tuple is `(intern_or_None, referral, risk_score_or_None, red_flags)`.
    """
    from app.modules.referral.models import AiParseResult, RiskProfile

    referral_rows = (
        await session.execute(
            select(Referral, Intern)
            .outerjoin(Intern, Intern.referral_id == Referral.id)
            .where(Referral.mentor_id == mentor_user_id)
            .order_by(Referral.created_at.desc())
        )
    ).all()
    if not referral_rows:
        return []

    referral_ids = [r.id for r, _ in referral_rows]

    risk_rows = (
        await session.execute(
            select(RiskProfile.referral_id, RiskProfile.risk_score).where(
                RiskProfile.referral_id.in_(referral_ids)
            )
        )
    ).all()
    risk_by_referral: dict[UUID, int] = {rid: score for rid, score in risk_rows}

    # AI-1 resume parse stores red_flags inside the raw_output JSONB.
    parse_rows = (
        await session.execute(
            select(AiParseResult.referral_id, AiParseResult.raw_output)
            .where(
                AiParseResult.referral_id.in_(referral_ids),
                AiParseResult.ai_touchpoint == "RESUME_PARSE",
            )
            .order_by(AiParseResult.parsed_at.desc())
        )
    ).all()
    flags_by_referral: dict[UUID, list[str]] = {}
    for rid, raw in parse_rows:
        if rid in flags_by_referral:
            continue  # keep newest only
        flags = raw.get("red_flags") if isinstance(raw, dict) else None
        if isinstance(flags, list):
            flags_by_referral[rid] = [str(f) for f in flags]

    return [
        (
            intern,
            referral,
            risk_by_referral.get(referral.id),
            flags_by_referral.get(referral.id, []),
        )
        for referral, intern in referral_rows
    ]


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
        except Exception:
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
    # Mentor can mark complete from any non-terminal in-progress state
    # (decision: eliminate manual-handoff stages — the AI-8 cert + cooling
    # apply identically regardless of where the closure was triggered).
    if ReferralStatus(referral.status) in TERMINAL_REFERRAL_STATUSES:
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
        except Exception:
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
    # Termination is allowed from any non-terminal state. Mentor / HR /
    # candidate can pull the plug at any stage of onboarding or active
    # internship; only re-terminating an already-terminal referral is
    # blocked (idempotency + audit clarity).
    if ReferralStatus(referral.status) in TERMINAL_REFERRAL_STATUSES:
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="TERMINATE"
        )

    previous_status = referral.status

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
            from_status=previous_status,
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
        except Exception:
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
