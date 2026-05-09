"""Mentor assignment lifecycle (Blueprint §4.1 phase 2 + F-08..F-12).

Entry points used by S1:
  * `request_assignment(...)` — first call right after a referral is
    submitted. Creates the `mentor_assignments` row, issues two action
    tokens, publishes `MentorAssignmentRequested`.
  * `accept(token, ...)` — RULE-M1 happy path. Transitions the
    referral to MENTOR_ACCEPTED and increments the mentor's mentee
    count.
  * `reject(token, reason, ...)` — RULE-M4. Captures reason + bumps
    `mentor_attempt_count`. If 3 attempts have failed, transitions to
    CANDIDATE_REJECTED (terminal, RULE-M3 — handled by the FSM/cooling
    helpers in S5; for S1 we set the status and publish the event).
  * `handle_timeouts(...)` — APScheduler entry point (RULE-M2). Marks
    expired pending assignments as TIMED_OUT, bumps `attempt_count`,
    invalidates the now-stale tokens.

The functions take a session — they don't open one. They expect the
caller (router or job) to manage the transaction. This keeps the audit
publish in the same transaction as the state change.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.mentor import action_tokens
from app.modules.referral.models import (
    MentorAssignment,
    Referral,
    ReferralStageHistory,
)
from app.shared.constants import (
    ACTION_TOKEN_EXPIRY_DAYS,
    AI_SYSTEM_USER_ID,
    MAX_MENTOR_ATTEMPTS,
    MENTOR_RESPONSE_DEADLINE_DAYS,
    ActionTokenType,
    MentorAssignmentStatus,
    ReferralStatus,
)
from app.shared.domain_events import (
    MentorAccepted,
    MentorAssignmentRequested,
    MentorRejected,
    MentorTimedOut,
)
from app.shared.exceptions import (
    InvalidStateTransitionError,
    MaxMentorAttemptsReachedError,
    MentorRejectionReasonMissingError,
)
from app.shared.value_objects import MentorAssignmentId, ReferralId, UserId

logger = logging.getLogger("nexhire.mentor")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ────────────────────────────────────────────────────────────────────
# Phase 1 — assignment request.
# ────────────────────────────────────────────────────────────────────
async def request_assignment(
    session: AsyncSession,
    *,
    referral_id: UUID,
    mentor_id: UUID,
    referrer_id: UUID,
) -> tuple[MentorAssignment, action_tokens.IssuedToken, action_tokens.IssuedToken]:
    """Persist a fresh assignment + issue accept/reject tokens.

    Returns the assignment row plus both raw tokens (the email handler
    composes URLs from them). The two tokens share `referral_id` so a
    response on one invalidates the other via `invalidate_siblings`.
    """
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one()

    if referral.status not in (
        ReferralStatus.SUBMITTED.value,
        ReferralStatus.MENTOR_PENDING.value,
    ):
        raise InvalidStateTransitionError(
            current_status=referral.status, attempted_action="REQUEST_MENTOR"
        )
    if referral.mentor_attempt_count >= MAX_MENTOR_ATTEMPTS:
        raise MaxMentorAttemptsReachedError()

    attempt_number = referral.mentor_attempt_count + 1
    timeout_at = _utcnow() + timedelta(days=MENTOR_RESPONSE_DEADLINE_DAYS)

    assignment = MentorAssignment(
        referral_id=referral.id,
        mentor_id=mentor_id,
        attempt_number=attempt_number,
        status=MentorAssignmentStatus.PENDING.value,
        timeout_at=timeout_at,
    )
    session.add(assignment)
    await session.flush()

    accept_token = await action_tokens.issue(
        session,
        action_type=ActionTokenType.MENTOR_RESPONSE,
        actor_user_id=mentor_id,
        referral_id=referral.id,
        expiry_days=ACTION_TOKEN_EXPIRY_DAYS,
    )
    reject_token = await action_tokens.issue(
        session,
        action_type=ActionTokenType.MENTOR_RESPONSE,
        actor_user_id=mentor_id,
        referral_id=referral.id,
        expiry_days=ACTION_TOKEN_EXPIRY_DAYS,
    )

    # FSM: SUBMITTED → MENTOR_PENDING (first attempt) or stay in
    # MENTOR_PENDING (later attempts). Either way, stage_entered_at
    # resets so the SLA clock starts from now.
    if referral.status == ReferralStatus.SUBMITTED.value:
        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=referral.status,
            to_status=ReferralStatus.MENTOR_PENDING.value,
            actor_id=referrer_id,
            actor_role="REFERRER",
            reason=f"Mentor assignment attempt {attempt_number}",
        )
    referral.status = ReferralStatus.MENTOR_PENDING.value
    referral.current_stage = ReferralStatus.MENTOR_PENDING.value
    referral.stage_entered_at = _utcnow()
    referral.updated_at = _utcnow()

    await audit.publish(
        event_type="MENTOR_ASSIGNED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=referrer_id,
        actor_role="REFERRER",
        payload={
            "mentor_id": str(mentor_id),
            "attempt_number": attempt_number,
            "timeout_at": timeout_at.isoformat(),
        },
        session=session,
    )

    return assignment, accept_token, reject_token


def _build_request_event(
    *,
    referral_id: UUID,
    mentor_id: UUID,
    assignment_id: UUID,
    attempt_number: int,
    accept_raw: str,
    reject_raw: str,
) -> MentorAssignmentRequested:
    return MentorAssignmentRequested(
        referral_id=ReferralId(referral_id),
        mentor_id=UserId(mentor_id),
        assignment_id=MentorAssignmentId(assignment_id),
        attempt_number=attempt_number,
        accept_token=accept_raw,
        reject_token=reject_raw,
    )


# ────────────────────────────────────────────────────────────────────
# Phase 2 — accept.
# ────────────────────────────────────────────────────────────────────
async def accept(
    session: AsyncSession,
    *,
    raw_token: str,
    ip_address: str | None = None,
) -> MentorAssignment:
    """Mentor clicks Accept. Token is consumed; sibling reject token
    is invalidated; referral transitions MENTOR_PENDING → MENTOR_ACCEPTED.
    """
    token_row = await action_tokens.validate(
        session,
        raw_token=raw_token,
        expected_action=ActionTokenType.MENTOR_RESPONSE,
        mark_used=True,
        ip_address=ip_address,
    )

    referral = (
        await session.execute(
            select(Referral).where(Referral.id == token_row.referral_id)
        )
    ).scalar_one()

    # Reassignment (decision A14) creates a fresh assignment without
    # bumping `mentor_attempt_count`, so the lookup is anchored to the
    # latest PENDING row instead of the counter.
    assignment = (
        await session.execute(
            select(MentorAssignment)
            .where(
                MentorAssignment.referral_id == referral.id,
                MentorAssignment.mentor_id == token_row.actor_user_id,
                MentorAssignment.status == MentorAssignmentStatus.PENDING.value,
            )
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise InvalidStateTransitionError(
            current_status=referral.status,
            attempted_action="ACCEPT",
        )

    now = _utcnow()
    assignment.status = MentorAssignmentStatus.ACCEPTED.value
    assignment.responded_at = now

    await action_tokens.invalidate_siblings(
        session,
        referral_id=referral.id,
        action_type=ActionTokenType.MENTOR_RESPONSE,
    )

    referral.status = ReferralStatus.MENTOR_ACCEPTED.value
    referral.current_stage = ReferralStatus.MENTOR_ACCEPTED.value
    referral.stage_entered_at = now
    referral.mentor_id = assignment.mentor_id
    referral.mentor_attempt_count += 1
    referral.updated_at = now

    _record_stage_history(
        session,
        referral_id=referral.id,
        from_status=ReferralStatus.MENTOR_PENDING.value,
        to_status=ReferralStatus.MENTOR_ACCEPTED.value,
        actor_id=assignment.mentor_id,
        actor_role="MENTOR",
        reason="Mentor accepted",
    )

    await audit.publish(
        event_type="MENTOR_ACCEPTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=assignment.mentor_id,
        actor_role="MENTOR",
        ip_address=ip_address,
        payload={"mentor_id": str(assignment.mentor_id)},
        session=session,
    )

    # Domain event — auto-approval engine subscribes to this.
    await get_bus().publish(
        MentorAccepted(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(assignment.mentor_id),
        )
    )

    return assignment


# ────────────────────────────────────────────────────────────────────
# Phase 3 — reject.
# ────────────────────────────────────────────────────────────────────
async def reject(
    session: AsyncSession,
    *,
    raw_token: str,
    reason: str,
    ip_address: str | None = None,
) -> tuple[MentorAssignment, bool]:
    """Mentor declines. Returns (assignment, is_terminal).

    `is_terminal=True` when this was the 3rd attempt — referral moves to
    CANDIDATE_REJECTED. The cooling-period write happens later in the
    referral service when the FSM commits the terminal transition.
    """
    if not reason or len(reason.strip()) < 10:
        raise MentorRejectionReasonMissingError()

    token_row = await action_tokens.validate(
        session,
        raw_token=raw_token,
        expected_action=ActionTokenType.MENTOR_RESPONSE,
        mark_used=True,
        ip_address=ip_address,
    )

    referral = (
        await session.execute(
            select(Referral).where(Referral.id == token_row.referral_id)
        )
    ).scalar_one()
    # See `accept` — anchor on the latest PENDING row, not on the counter.
    assignment = (
        await session.execute(
            select(MentorAssignment)
            .where(
                MentorAssignment.referral_id == referral.id,
                MentorAssignment.mentor_id == token_row.actor_user_id,
                MentorAssignment.status == MentorAssignmentStatus.PENDING.value,
            )
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise InvalidStateTransitionError(
            current_status=referral.status,
            attempted_action="REJECT",
        )

    now = _utcnow()
    assignment.status = MentorAssignmentStatus.REJECTED.value
    assignment.responded_at = now
    assignment.rejection_reason = reason.strip()

    await action_tokens.invalidate_siblings(
        session,
        referral_id=referral.id,
        action_type=ActionTokenType.MENTOR_RESPONSE,
    )

    referral.mentor_attempt_count += 1
    is_terminal = referral.mentor_attempt_count >= MAX_MENTOR_ATTEMPTS
    if is_terminal:
        referral.status = ReferralStatus.CANDIDATE_REJECTED.value
        referral.current_stage = ReferralStatus.CANDIDATE_REJECTED.value
        referral.rejected_at = now
        referral.rejection_reason = "MAX_MENTOR_ATTEMPTS_EXCEEDED"
        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_PENDING.value,
            to_status=ReferralStatus.CANDIDATE_REJECTED.value,
            actor_id=assignment.mentor_id,
            actor_role="MENTOR",
            reason="Max mentor attempts exceeded after rejection",
        )
    else:
        referral.status = ReferralStatus.MENTOR_PENDING.value
        referral.current_stage = ReferralStatus.MENTOR_PENDING.value
        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_PENDING.value,
            to_status=ReferralStatus.MENTOR_PENDING.value,
            actor_id=assignment.mentor_id,
            actor_role="MENTOR",
            reason=f"Mentor rejected attempt {assignment.attempt_number}: {reason[:200]}",
        )

    referral.stage_entered_at = now
    referral.updated_at = now

    await audit.publish(
        event_type="MENTOR_REJECTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=assignment.mentor_id,
        actor_role="MENTOR",
        ip_address=ip_address,
        payload={
            "mentor_id": str(assignment.mentor_id),
            "attempt_number": assignment.attempt_number,
            "reason": reason[:500],
            "is_terminal": is_terminal,
        },
        session=session,
    )

    await get_bus().publish(
        MentorRejected(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(assignment.mentor_id),
            attempt_number=assignment.attempt_number,
            reason=reason[:500],
            is_terminal=is_terminal,
        )
    )

    return assignment, is_terminal


# ────────────────────────────────────────────────────────────────────
# In-app accept / reject — used from the mentor dashboard. The token
# flow above is unchanged (email link path); these helpers do the same
# work but authenticate via the mentor's JWT instead of an email token.
# ────────────────────────────────────────────────────────────────────
async def accept_by_mentor(
    session: AsyncSession,
    *,
    referral_id: UUID,
    mentor_user_id: UUID,
    ip_address: str | None = None,
) -> MentorAssignment:
    """Mentor accepts from the dashboard. Mirrors `accept(raw_token=...)`."""
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise InvalidStateTransitionError(
            current_status="MISSING", attempted_action="ACCEPT"
        )

    # Look up the active PENDING assignment for this mentor + referral.
    # Reassignment (decision A14) creates a fresh assignment without
    # bumping `mentor_attempt_count`, so we can't anchor the lookup to
    # `attempt_number == count + 1` — pick the latest pending row instead.
    assignment = (
        await session.execute(
            select(MentorAssignment)
            .where(
                MentorAssignment.referral_id == referral.id,
                MentorAssignment.mentor_id == mentor_user_id,
                MentorAssignment.status == MentorAssignmentStatus.PENDING.value,
            )
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if assignment is None:
        all_rows = (
            await session.execute(
                select(MentorAssignment).where(
                    MentorAssignment.referral_id == referral.id
                )
            )
        ).scalars().all()
        rows_summary = ", ".join(
            f"[mentor={row.mentor_id} attempt={row.attempt_number} status={row.status}]"
            for row in all_rows
        ) or "<no rows>"
        diag = (
            f"accept_by_mentor lookup miss: "
            f"referral_id={referral.id} "
            f"principal_user_id={mentor_user_id} "
            f"referral_mentor_id={referral.mentor_id} "
            f"referral_status={referral.status} "
            f"mentor_attempt_count={referral.mentor_attempt_count} "
            f"assignment_rows={rows_summary}"
        )
        logger.warning(diag)
        raise InvalidStateTransitionError(
            current_status=f"{referral.status} (DEBUG: {rows_summary})",
            attempted_action="ACCEPT",
        )

    now = _utcnow()
    assignment.status = MentorAssignmentStatus.ACCEPTED.value
    assignment.responded_at = now

    # Invalidate the still-outstanding accept/reject email tokens so the
    # mentor can't double-respond from their inbox.
    await action_tokens.invalidate_siblings(
        session,
        referral_id=referral.id,
        action_type=ActionTokenType.MENTOR_RESPONSE,
    )

    referral.status = ReferralStatus.MENTOR_ACCEPTED.value
    referral.current_stage = ReferralStatus.MENTOR_ACCEPTED.value
    referral.stage_entered_at = now
    referral.mentor_id = assignment.mentor_id
    referral.mentor_attempt_count += 1
    referral.updated_at = now

    _record_stage_history(
        session,
        referral_id=referral.id,
        from_status=ReferralStatus.MENTOR_PENDING.value,
        to_status=ReferralStatus.MENTOR_ACCEPTED.value,
        actor_id=assignment.mentor_id,
        actor_role="MENTOR",
        reason="Mentor accepted (dashboard)",
    )

    await audit.publish(
        event_type="MENTOR_ACCEPTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=assignment.mentor_id,
        actor_role="MENTOR",
        ip_address=ip_address,
        payload={"mentor_id": str(assignment.mentor_id), "via": "dashboard"},
        session=session,
    )

    await get_bus().publish(
        MentorAccepted(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(assignment.mentor_id),
        )
    )

    return assignment


async def reject_by_mentor(
    session: AsyncSession,
    *,
    referral_id: UUID,
    mentor_user_id: UUID,
    reason: str,
    ip_address: str | None = None,
) -> tuple[MentorAssignment, bool]:
    """Mentor declines from the dashboard. Mirrors `reject(raw_token=...)`."""
    if not reason or len(reason.strip()) < 10:
        raise MentorRejectionReasonMissingError()

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise InvalidStateTransitionError(
            current_status="MISSING", attempted_action="REJECT"
        )

    # See `accept_by_mentor` — pick the latest PENDING row for this
    # mentor + referral so reassigned attempts (which don't bump the
    # counter) can still be rejected from the dashboard.
    assignment = (
        await session.execute(
            select(MentorAssignment)
            .where(
                MentorAssignment.referral_id == referral.id,
                MentorAssignment.mentor_id == mentor_user_id,
                MentorAssignment.status == MentorAssignmentStatus.PENDING.value,
            )
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise InvalidStateTransitionError(
            current_status=referral.status,
            attempted_action="REJECT",
        )

    now = _utcnow()
    assignment.status = MentorAssignmentStatus.REJECTED.value
    assignment.responded_at = now
    assignment.rejection_reason = reason.strip()

    await action_tokens.invalidate_siblings(
        session,
        referral_id=referral.id,
        action_type=ActionTokenType.MENTOR_RESPONSE,
    )

    referral.mentor_attempt_count += 1
    is_terminal = referral.mentor_attempt_count >= MAX_MENTOR_ATTEMPTS
    if is_terminal:
        referral.status = ReferralStatus.CANDIDATE_REJECTED.value
        referral.current_stage = ReferralStatus.CANDIDATE_REJECTED.value
        referral.rejected_at = now
        referral.rejection_reason = "MAX_MENTOR_ATTEMPTS_EXCEEDED"
        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_PENDING.value,
            to_status=ReferralStatus.CANDIDATE_REJECTED.value,
            actor_id=assignment.mentor_id,
            actor_role="MENTOR",
            reason="Max mentor attempts exceeded after rejection",
        )
    else:
        referral.status = ReferralStatus.MENTOR_PENDING.value
        referral.current_stage = ReferralStatus.MENTOR_PENDING.value
        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_PENDING.value,
            to_status=ReferralStatus.MENTOR_PENDING.value,
            actor_id=assignment.mentor_id,
            actor_role="MENTOR",
            reason=f"Mentor rejected attempt {assignment.attempt_number} (dashboard): {reason[:200]}",
        )

    referral.stage_entered_at = now
    referral.updated_at = now

    await audit.publish(
        event_type="MENTOR_REJECTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=assignment.mentor_id,
        actor_role="MENTOR",
        ip_address=ip_address,
        payload={
            "mentor_id": str(assignment.mentor_id),
            "attempt_number": assignment.attempt_number,
            "reason": reason[:500],
            "is_terminal": is_terminal,
            "via": "dashboard",
        },
        session=session,
    )

    await get_bus().publish(
        MentorRejected(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(assignment.mentor_id),
            attempt_number=assignment.attempt_number,
            reason=reason[:500],
            is_terminal=is_terminal,
        )
    )

    return assignment, is_terminal


# ────────────────────────────────────────────────────────────────────
# Phase 4 — timeouts (APScheduler entry point).
# ────────────────────────────────────────────────────────────────────
async def handle_timeouts(session: AsyncSession) -> int:
    """Find pending assignments whose `timeout_at` has passed.

    For each: mark TIMED_OUT, bump attempt_count, invalidate tokens,
    transition referral status. Returns the number of timeouts handled.
    """
    pending = (
        await session.execute(
            select(MentorAssignment).where(
                MentorAssignment.status == MentorAssignmentStatus.PENDING.value,
                MentorAssignment.timeout_at <= _utcnow(),
            )
        )
    ).scalars().all()

    if not pending:
        return 0

    handled = 0
    for assignment in pending:
        referral = (
            await session.execute(
                select(Referral).where(Referral.id == assignment.referral_id)
            )
        ).scalar_one()

        now = _utcnow()
        # Idempotency: if the attempt counter has already advanced past
        # this assignment's number, skip — another path resolved it.
        if assignment.attempt_number != referral.mentor_attempt_count + 1:
            continue
        if referral.status not in (
            ReferralStatus.MENTOR_PENDING.value,
            ReferralStatus.SUBMITTED.value,
        ):
            continue

        assignment.status = MentorAssignmentStatus.TIMED_OUT.value
        assignment.responded_at = now

        await action_tokens.invalidate_siblings(
            session,
            referral_id=referral.id,
            action_type=ActionTokenType.MENTOR_RESPONSE,
        )

        referral.mentor_attempt_count += 1
        is_terminal = referral.mentor_attempt_count >= MAX_MENTOR_ATTEMPTS
        if is_terminal:
            referral.status = ReferralStatus.CANDIDATE_REJECTED.value
            referral.current_stage = ReferralStatus.CANDIDATE_REJECTED.value
            referral.rejected_at = now
            referral.rejection_reason = "MAX_MENTOR_ATTEMPTS_EXCEEDED"
        else:
            referral.status = ReferralStatus.MENTOR_PENDING.value
            referral.current_stage = ReferralStatus.MENTOR_PENDING.value
        referral.stage_entered_at = now
        referral.updated_at = now

        _record_stage_history(
            session,
            referral_id=referral.id,
            from_status=ReferralStatus.MENTOR_PENDING.value,
            to_status=referral.status,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason=f"Mentor attempt {assignment.attempt_number} timed out",
        )

        await audit.publish(
            event_type="MENTOR_TIMED_OUT",
            entity_type="REFERRAL",
            entity_id=referral.id,
            actor_user_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            payload={
                "mentor_id": str(assignment.mentor_id),
                "attempt_number": assignment.attempt_number,
                "is_terminal": is_terminal,
            },
            session=session,
        )
        await get_bus().publish(
            MentorTimedOut(
                referral_id=ReferralId(referral.id),
                mentor_id=UserId(assignment.mentor_id),
                attempt_number=assignment.attempt_number,
                is_terminal=is_terminal,
            )
        )
        handled += 1

    return handled


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
def _record_stage_history(
    session: AsyncSession,
    *,
    referral_id: UUID,
    from_status: str,
    to_status: str,
    actor_id: UUID | None,
    actor_role: str | None,
    reason: str | None = None,
) -> None:
    session.add(
        ReferralStageHistory(
            referral_id=referral_id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
        )
    )


# ────────────────────────────────────────────────────────────────────
# A14 — HR mid-flow reassignment.
# ────────────────────────────────────────────────────────────────────
async def reassign_by_hr(
    session: AsyncSession,
    *,
    referral_id: UUID,
    new_mentor_id: UUID,
    hr_user_id: UUID,
    hr_role: str,
    reason: str,
) -> MentorAssignment:
    """Replace the active mentor mid-flow.

    Decision A14:
      * Allowed from any state in MENTOR_ACCEPTED..ACTIVE.
      * Doesn't bump `mentor_attempt_count` — different scenario from rejection.
      * Marks the current `mentor_assignments` row REASSIGNED with `reassigned_*`.
      * Creates a fresh PENDING assignment for `new_mentor_id` with the
        next available `attempt_number`.
      * Issues 2 new action tokens for the new mentor.
      * Reverts referral status to MENTOR_PENDING; FSM transitions resume
        from there (notification, timeout, etc.).
      * NDA / ID / AD progress on the referral is preserved (for S3+).

    Validations:
      * Caller is HR or PROGRAM_OWNER.
      * `new_mentor_id != current mentor_id`.
      * `new_mentor_id != referrer_id` (RULE-E3).
      * New mentor has capacity (live threshold).
      * Reason ≥ 10 characters.
    """
    from app.modules.referral import validator
    from app.shared.constants import UserRole
    from app.shared.domain_events import MentorReassigned
    from app.shared.exceptions import (
        BusinessRuleError,
        InsufficientPermissionsError,
        ReferrerIsMentorError,
    )

    if hr_role not in (UserRole.HR.value, UserRole.PROGRAM_OWNER.value):
        raise InsufficientPermissionsError()
    if not reason or len(reason.strip()) < 10:
        raise BusinessRuleError(
            user_message="Reassignment reason must be at least 10 characters.",
            details={"min_length": 10},
        )

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise BusinessRuleError(
            user_message="Referral not found.",
            details={"referral_id": str(referral_id)},
        )

    allowed_source_states = {
        ReferralStatus.MENTOR_ACCEPTED.value,
        ReferralStatus.HR_REVIEW.value,
        ReferralStatus.APPROVED.value,
        ReferralStatus.JOINING_FORM_PENDING.value,
        ReferralStatus.JOINING_FORM_SUBMITTED.value,
        ReferralStatus.JOINING_FORM_LOCKED.value,
        ReferralStatus.ID_PENDING.value,
        ReferralStatus.ID_ISSUED.value,
        ReferralStatus.NDA_PENDING.value,
        ReferralStatus.NDA_SIGNED.value,
        ReferralStatus.ACCESS_PENDING.value,
        ReferralStatus.ACTIVE.value,
        ReferralStatus.EXTENDED.value,
    }
    if referral.status not in allowed_source_states:
        raise InvalidStateTransitionError(
            current_status=referral.status,
            attempted_action="MENTOR_REASSIGN",
        )

    if new_mentor_id == referral.referrer_id:
        raise ReferrerIsMentorError()
    if referral.mentor_id == new_mentor_id:
        raise BusinessRuleError(
            user_message="The selected mentor is already assigned to this referral.",
        )

    await validator.validate_mentor_capacity(session, mentor_id=new_mentor_id)

    # ── Mark current assignment as REASSIGNED ────────────────────
    current = (
        await session.execute(
            select(MentorAssignment)
            .where(
                MentorAssignment.referral_id == referral.id,
                MentorAssignment.status.in_(
                    (
                        MentorAssignmentStatus.PENDING.value,
                        MentorAssignmentStatus.ACCEPTED.value,
                    )
                ),
            )
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    now = _utcnow()
    original_mentor_id = referral.mentor_id
    if current is not None:
        current.status = MentorAssignmentStatus.REASSIGNED.value
        current.reassigned_to = new_mentor_id
        current.reassigned_at = now
        current.reassigned_by = hr_user_id
        current.reassign_reason = reason.strip()

    # Invalidate any still-pending action tokens on the old mentor.
    await action_tokens.invalidate_siblings(
        session,
        referral_id=referral.id,
        action_type=ActionTokenType.MENTOR_RESPONSE,
    )

    # ── Create the new pending assignment ────────────────────────
    next_attempt = (
        await session.execute(
            select(MentorAssignment.attempt_number)
            .where(MentorAssignment.referral_id == referral.id)
            .order_by(MentorAssignment.attempt_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    next_attempt = (next_attempt or 0) + 1

    new_assignment = MentorAssignment(
        referral_id=referral.id,
        mentor_id=new_mentor_id,
        attempt_number=next_attempt,
        status=MentorAssignmentStatus.PENDING.value,
        timeout_at=now + timedelta(days=MENTOR_RESPONSE_DEADLINE_DAYS),
    )
    session.add(new_assignment)
    await session.flush()

    accept_token = await action_tokens.issue(
        session,
        action_type=ActionTokenType.MENTOR_RESPONSE,
        actor_user_id=new_mentor_id,
        referral_id=referral.id,
        expiry_days=ACTION_TOKEN_EXPIRY_DAYS,
    )
    reject_token = await action_tokens.issue(
        session,
        action_type=ActionTokenType.MENTOR_RESPONSE,
        actor_user_id=new_mentor_id,
        referral_id=referral.id,
        expiry_days=ACTION_TOKEN_EXPIRY_DAYS,
    )

    # ── Revert the referral to MENTOR_PENDING + tracking. We DO NOT
    # touch `mentor_attempt_count` (decision A14: doesn't reset / count).
    previous_status = referral.status
    referral.mentor_id = new_mentor_id
    referral.status = ReferralStatus.MENTOR_PENDING.value
    referral.current_stage = ReferralStatus.MENTOR_PENDING.value
    referral.stage_entered_at = now
    referral.updated_at = now

    _record_stage_history(
        session,
        referral_id=referral.id,
        from_status=previous_status,
        to_status=ReferralStatus.MENTOR_PENDING.value,
        actor_id=hr_user_id,
        actor_role=hr_role,
        reason=f"Mentor reassigned by HR: {reason[:200]}",
    )

    await audit.publish(
        event_type="MENTOR_REASSIGNED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=hr_user_id,
        actor_role=hr_role,
        payload={
            "original_mentor_id": str(original_mentor_id) if original_mentor_id else None,
            "new_mentor_id": str(new_mentor_id),
            "previous_status": previous_status,
            "reason": reason[:500],
            "new_assignment_id": str(new_assignment.id),
            "new_attempt_number": next_attempt,
        },
        session=session,
    )

    bus = get_bus()
    if original_mentor_id is not None:
        await bus.publish(
            MentorReassigned(
                referral_id=ReferralId(referral.id),
                original_mentor_id=UserId(original_mentor_id),
                new_mentor_id=UserId(new_mentor_id),
                hr_actor_id=UserId(hr_user_id),
                reason=reason[:500],
            )
        )
    await bus.publish(
        MentorAssignmentRequested(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(new_mentor_id),
            assignment_id=MentorAssignmentId(new_assignment.id),
            attempt_number=next_attempt,
            accept_token=accept_token.raw_token,
            reject_token=reject_token.raw_token,
        )
    )

    return new_assignment


__all__ = [
    "_build_request_event",
    "accept",
    "handle_timeouts",
    "reassign_by_hr",
    "reject",
    "request_assignment",
]
