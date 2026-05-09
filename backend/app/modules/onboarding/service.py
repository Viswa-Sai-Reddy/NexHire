"""Joining-form service.

Operations the candidate portal calls:
  * `get_or_create_form(intern_id)` — returns the candidate's draft.
  * `save_draft(intern_id, payload)` — auto-save every 60s. Optimistic
    locking via the `version` column.
  * `submit(intern_id)` — DRAFT/SUBMITTED → SUBMITTED; fires the
    auto-lock engine, which always auto-locks (flags are recorded for
    audit / HR recall but no longer gate the transition).

Operations HR calls (S13/S14):
  * `manual_lock(intern_id, hr_user_id)` — flagged path; HR locks after
    review. Closes the JOINING_FORM_REVIEW task. Triggers F-34 NW-ID
    auto-gen.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.onboarding import auto_lock
from app.modules.onboarding.models import Intern, JoiningForm
from app.modules.referral.models import (
    Referral,
    ReferralStageHistory,
    Task,
)
from app.shared.constants import (
    JoiningFormStatus,
    ReferralStatus,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
    InvalidStateTransitionError,
    JoiningFormAlreadyLockedError,
    JoiningFormVersionConflictError,
)

logger = logging.getLogger("nexhire.onboarding.service")


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def get_form(session: AsyncSession, *, intern_id: UUID) -> JoiningForm:
    form = (
        await session.execute(
            select(JoiningForm).where(JoiningForm.intern_id == intern_id)
        )
    ).scalar_one_or_none()
    if form is None:
        raise BusinessRuleError(
            user_message="Joining form not found.",
            details={"intern_id": str(intern_id)},
        )
    return form


async def save_draft(
    session: AsyncSession,
    *,
    intern_id: UUID,
    expected_version: int,
    fields: dict[str, Any],
) -> JoiningForm:
    form = await get_form(session, intern_id=intern_id)
    if form.status == JoiningFormStatus.LOCKED.value:
        raise JoiningFormAlreadyLockedError()
    if form.version != expected_version:
        raise JoiningFormVersionConflictError(
            details={"current_version": form.version, "client_version": expected_version}
        )

    for key, value in fields.items():
        if hasattr(form, key) and key not in {"id", "intern_id", "version", "status"}:
            setattr(form, key, value)
    form.version += 1
    form.updated_at = _utcnow()
    return form


async def submit(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> auto_lock.AutoLockResult:
    """Candidate submits. Status → SUBMITTED, then the auto-lock engine
    always auto-locks (flags recorded for audit, no HR gate).
    """
    form = await get_form(session, intern_id=intern_id)
    if form.status == JoiningFormStatus.LOCKED.value:
        raise JoiningFormAlreadyLockedError()
    if not form.declaration_signed:
        raise BusinessRuleError(
            user_message="Please sign the declaration before submitting."
        )
    if form.status == JoiningFormStatus.DRAFT.value:
        form.status = JoiningFormStatus.SUBMITTED.value
        form.submitted_at = _utcnow()
        form.version += 1
        form.updated_at = _utcnow()

    referral = (
        await session.execute(
            select(Referral)
            .join(Intern, Intern.referral_id == Referral.id)
            .where(Intern.id == intern_id)
        )
    ).scalar_one()
    if referral.status in (
        ReferralStatus.JOINING_FORM_PENDING.value,
        ReferralStatus.APPROVED.value,
        ReferralStatus.CORRECTION_NEEDED.value,
    ):
        referral.status = ReferralStatus.JOINING_FORM_SUBMITTED.value
        referral.current_stage = ReferralStatus.JOINING_FORM_SUBMITTED.value
        referral.stage_entered_at = _utcnow()
        referral.updated_at = _utcnow()
        session.add(
            ReferralStageHistory(
                referral_id=referral.id,
                from_status=ReferralStatus.JOINING_FORM_PENDING.value,
                to_status=ReferralStatus.JOINING_FORM_SUBMITTED.value,
                actor_id=None,
                actor_role="CANDIDATE",
                reason="Joining form submitted.",
            )
        )

    await audit.publish(
        event_type="JOINING_FORM_SUBMITTED",
        entity_type="INTERN",
        entity_id=intern_id,
        actor_user_id=None,
        actor_role="CANDIDATE",
        payload={"referral_id": str(referral.id), "version": form.version},
        session=session,
    )

    return await auto_lock.evaluate_and_route(session, intern_id=intern_id)


async def manual_lock(
    session: AsyncSession,
    *,
    intern_id: UUID,
    hr_user_id: UUID,
    hr_role: UserRole,
    notes: str | None = None,
) -> JoiningForm:
    """HR locks a flagged form after review. Triggers F-34."""
    if hr_role not in (UserRole.HR, UserRole.PROGRAM_OWNER):
        raise InsufficientPermissionsError()

    form = await get_form(session, intern_id=intern_id)
    if form.status == JoiningFormStatus.LOCKED.value:
        raise JoiningFormAlreadyLockedError()
    if form.status != JoiningFormStatus.SUBMITTED.value:
        raise InvalidStateTransitionError(
            current_status=form.status, attempted_action="JOINING_FORM_LOCK"
        )

    now = _utcnow()
    form.status = JoiningFormStatus.LOCKED.value
    form.locked_at = now
    form.locked_by = hr_user_id
    form.locked_by_label = "HR"
    form.version += 1
    form.updated_at = now

    referral = (
        await session.execute(
            select(Referral)
            .join(Intern, Intern.referral_id == Referral.id)
            .where(Intern.id == intern_id)
        )
    ).scalar_one()
    referral.status = ReferralStatus.JOINING_FORM_LOCKED.value
    referral.current_stage = ReferralStatus.JOINING_FORM_LOCKED.value
    referral.stage_entered_at = now
    referral.updated_at = now

    # Close the open JOINING_FORM_REVIEW task.
    task = (
        await session.execute(
            select(Task)
            .where(
                Task.intern_id == intern_id,
                Task.task_type == TaskType.JOINING_FORM_REVIEW.value,
                Task.status == TaskStatus.PENDING.value,
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if task is not None:
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = now
        task.completed_by = hr_user_id
        task.completion_notes = notes

    await audit.publish(
        event_type="JOINING_FORM_LOCKED",
        entity_type="INTERN",
        entity_id=intern_id,
        actor_user_id=hr_user_id,
        actor_role=hr_role.value,
        payload={"notes": notes, "by_label": "HR"},
        session=session,
    )

    await get_bus().publish(
        auto_lock.JoiningFormLocked(
            intern_id=intern_id, referral_id=referral.id, auto_locked=False
        )
    )
    return form


# NOTE: NW-ID generation used to live here as an event handler subscribed
# to JoiningFormLocked. It now runs inline inside `auto_lock._auto_lock`
# so it shares the lock's transaction — silent rollbacks no longer
# leave a candidate locked without a Non-Worker ID.


__all__ = [
    "get_form",
    "manual_lock",
    "save_draft",
    "submit",
]
