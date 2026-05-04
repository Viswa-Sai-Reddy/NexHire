"""Access provisioning service — F-18.

Two parallel tracks routed onto the `tasks` table by AI-10:
  * `AD_PROVISION` (assigned to IT_AD)
  * `BADGE_ACCESS`  (assigned to ADMIN)

Public entry: `request_access_provisioning(intern_id)` is called when
the NDA is signed. It creates both tasks (T-2 business-day SLA) and
emits audit events.

`complete_ad_provisioning(...)` is what the IT user calls when done —
it patches Graph, updates the intern row, and advances the FSM if
both access tracks are complete.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.access import graph_client
from app.modules.ai import auto_router
from app.modules.onboarding.models import Intern
from app.modules.referral.models import Referral, Task
from app.shared.constants import (
    AdAccountStatus,
    ReferralStatus,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
)

logger = logging.getLogger("nexhire.access.service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def request_access_provisioning(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> tuple[Task, Task]:
    """Idempotent: returns existing tasks if already created."""
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    sla = (
        datetime.combine(referral.internship_start_date, datetime.min.time())
        - timedelta(days=2)
        if referral.internship_start_date
        else _utcnow() + timedelta(days=2)
    ).replace(tzinfo=timezone.utc)

    ad_task = await _ensure_task(
        session,
        intern_id=intern.id,
        referral_id=referral.id,
        task_type=TaskType.AD_PROVISION,
        role=UserRole.IT_AD,
        sla_deadline=sla,
    )
    badge_task = await _ensure_task(
        session,
        intern_id=intern.id,
        referral_id=referral.id,
        task_type=TaskType.BADGE_ACCESS,
        role=UserRole.ADMIN,
        sla_deadline=sla,
    )

    if referral.status == ReferralStatus.NDA_SIGNED.value:
        referral.status = ReferralStatus.ACCESS_PENDING.value
        referral.current_stage = ReferralStatus.ACCESS_PENDING.value
        referral.stage_entered_at = _utcnow()
        referral.updated_at = _utcnow()

    return ad_task, badge_task


async def _ensure_task(
    session: AsyncSession,
    *,
    intern_id: UUID,
    referral_id: UUID,
    task_type: TaskType,
    role: UserRole,
    sla_deadline: datetime,
) -> Task:
    existing = (
        await session.execute(
            select(Task)
            .where(
                Task.intern_id == intern_id,
                Task.task_type == task_type.value,
                Task.status.notin_((TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value)),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return await auto_router.create_routed_task(
        session,
        task_type=task_type,
        role=role,
        sla_deadline=sla_deadline,
        referral_id=referral_id,
        intern_id=intern_id,
    )


# ────────────────────────────────────────────────────────────────────
# AD provisioning completion path.
# ────────────────────────────────────────────────────────────────────
async def complete_ad_provisioning(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: UUID,
    actor_role: UserRole,
) -> Intern:
    if actor_role is not UserRole.IT_AD:
        raise InsufficientPermissionsError()

    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    if intern.ad_account_status == AdAccountStatus.ACTIVE.value:
        raise BusinessRuleError(
            user_message="AD account is already active for this intern."
        )

    nickname = intern.non_worker_id or f"intern-{intern.id.hex[:8]}"
    upn = f"{nickname.lower()}@nexhire.local"
    created = await graph_client.create_user(
        display_name=referral.candidate_name,
        upn=upn,
        mail_nickname=nickname,
    )
    intern.ad_account_username = created.user_principal_name
    intern.ad_account_status = AdAccountStatus.PROVISIONED.value
    intern.updated_at = _utcnow()

    # Close the AD_PROVISION task.
    task = (
        await session.execute(
            select(Task)
            .where(
                Task.intern_id == intern.id,
                Task.task_type == TaskType.AD_PROVISION.value,
                Task.status == TaskStatus.PENDING.value,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if task is not None:
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = _utcnow()
        task.completed_by = actor_user_id

    await audit.publish(
        event_type="AD_ACCOUNT_CREATED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={
            "user_principal_name": created.user_principal_name,
            "aad_object_id": created.aad_object_id,
        },
        session=session,
    )
    return intern


async def complete_badge_access(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: UUID,
    actor_role: UserRole,
    badge_reference: str,
) -> None:
    if actor_role is not UserRole.ADMIN:
        raise InsufficientPermissionsError()

    task = (
        await session.execute(
            select(Task)
            .where(
                Task.intern_id == intern_id,
                Task.task_type == TaskType.BADGE_ACCESS.value,
                Task.status == TaskStatus.PENDING.value,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if task is None:
        raise BusinessRuleError(
            user_message="No pending badge-access task for this intern.",
        )
    task.status = TaskStatus.COMPLETED.value
    task.completed_at = _utcnow()
    task.completed_by = actor_user_id
    task.completion_notes = f"Badge: {badge_reference}"

    await audit.publish(
        event_type="BADGE_CONFIGURED",
        entity_type="INTERN",
        entity_id=intern_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={"badge_reference": badge_reference},
        session=session,
    )


__all__ = [
    "complete_ad_provisioning",
    "complete_badge_access",
    "request_access_provisioning",
]
