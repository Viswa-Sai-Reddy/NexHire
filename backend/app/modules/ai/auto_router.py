"""AI-10 — Workflow Auto-Router.

Deterministic, no LLM. Given (task_type, role_group), pick the team
member who's:
  1. active (`is_active = true`),
  2. not OOO right now (`out_of_office_until > NOW()` excludes them),
  3. has the lowest count of open tasks,
  4. tie-breaker: fastest historical avg response on completed tasks.

If nobody qualifies (everyone OOO, or no users with that role), fall
back to the oldest active user in the role and surface a system alert
through the audit log so ops can see the resource squeeze.

The routing decision is captured on the task row (`assigned_by_ai`,
`ai_routing_reason`) and an audit event `AI_TASK_ROUTED` is published
inside the same transaction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.referral.models import Task
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    TaskStatus,
    TaskType,
    UserRole,
)

logger = logging.getLogger("nexhire.ai.auto_router")

MODEL_TOUCHPOINT = "WORKFLOW_ROUTING"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Returned by `pick_assignee` so the caller can persist + audit
    the decision atomically with the task it just created.
    """

    user_id: UUID
    open_task_count: int
    avg_response_hours: float | None
    reason: str
    fallback_used: bool = False


async def pick_assignee(
    session: AsyncSession,
    *,
    role: UserRole,
) -> RoutingDecision:
    """Choose the least-loaded user in `role`.

    The query lives in raw SQL because it spans `users` + `tasks` with
    aggregate filters and the SQLAlchemy ORM idioms get noisy. We do
    NOT hold a row-level lock — workload is "approximately even", not
    a strict invariant; concurrent assignments tolerate small drift.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT u.id,
                       u.full_name,
                       COUNT(t.id) FILTER (
                           WHERE t.status NOT IN ('COMPLETED', 'CANCELLED')
                       ) AS open_count,
                       AVG(
                           EXTRACT(EPOCH FROM (t.completed_at - t.created_at)) / 3600.0
                       ) FILTER (
                           WHERE t.status = 'COMPLETED'
                             AND t.completed_at IS NOT NULL
                       ) AS avg_response_hours
                FROM users u
                LEFT JOIN tasks t ON t.assigned_to = u.id
                WHERE u.role = :role
                  AND u.is_active = true
                  AND (
                      u.out_of_office_until IS NULL
                      OR u.out_of_office_until <= NOW()
                  )
                GROUP BY u.id, u.full_name
                ORDER BY open_count ASC NULLS FIRST,
                         avg_response_hours ASC NULLS LAST,
                         u.created_at ASC
                """
            ).bindparams(role=role.value)
        )
    ).mappings().all()

    if rows:
        chosen = rows[0]
        return RoutingDecision(
            user_id=cast("UUID", chosen["id"]),
            open_task_count=int(chosen["open_count"] or 0),
            avg_response_hours=(
                float(chosen["avg_response_hours"])
                if chosen["avg_response_hours"] is not None
                else None
            ),
            reason=_format_reason(
                int(chosen["open_count"] or 0),
                chosen["avg_response_hours"],
            ),
        )

    return await _fallback(session, role=role)


async def _fallback(
    session: AsyncSession, *, role: UserRole
) -> RoutingDecision:
    """All available members are OOO or none exist. Assign to the
    oldest active user in role; alert ops via audit.
    """
    fallback = (
        await session.execute(
            text(
                """
                SELECT id FROM users
                WHERE role = :role AND is_active = true
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).bindparams(role=role.value)
        )
    ).scalar_one_or_none()
    if fallback is None:
        # No one with this role at all — surface a fatal-ish error.
        await audit.publish_system_event(
            event_type="AI_AUTO_ROUTER_NO_ASSIGNEE",
            entity_type="ROLE",
            payload={"role": role.value},
        )
        raise RuntimeError(
            f"No active user found with role {role.value!r} for auto-routing."
        )

    await audit.publish_system_event(
        event_type="AI_AUTO_ROUTER_FALLBACK_USED",
        entity_type="ROLE",
        payload={
            "role": role.value,
            "reason": "All available role members were OOO; "
            "fell back to the role's oldest active member.",
        },
    )
    return RoutingDecision(
        user_id=cast("UUID", fallback),
        open_task_count=0,
        avg_response_hours=None,
        reason="Fallback: all role members OOO; assigned oldest active member.",
        fallback_used=True,
    )


def _format_reason(open_count: int, avg_hours: float | None) -> str:
    if avg_hours is None:
        return f"Lowest workload ({open_count} open tasks); no historical response data yet."
    return (
        f"Lowest workload ({open_count} open tasks), "
        f"fastest avg response ({avg_hours:.1f}h)."
    )


# ────────────────────────────────────────────────────────────────────
# Convenience: one-shot "create a routed task". Most callers want this.
# ────────────────────────────────────────────────────────────────────
async def create_routed_task(
    session: AsyncSession,
    *,
    task_type: TaskType,
    role: UserRole,
    sla_deadline: datetime,
    referral_id: UUID | None = None,
    intern_id: UUID | None = None,
) -> Task:
    """Pick an assignee + persist the Task + audit event.

    Idempotency: callers (e.g. auto-approval engine) ensure they don't
    create duplicate tasks for the same anchor. The router itself does
    no dedup — that's a domain concern, not a routing concern.
    """
    decision = await pick_assignee(session, role=role)

    task = Task(
        task_type=task_type.value,
        assigned_to=decision.user_id,
        sla_deadline=sla_deadline,
        referral_id=referral_id,
        intern_id=intern_id,
        assigned_by_ai=True,
        ai_routing_reason=decision.reason,
        status=TaskStatus.PENDING.value,
    )
    session.add(task)
    await session.flush()

    await audit.publish(
        event_type="AI_TASK_ROUTED",
        entity_type="TASK",
        entity_id=task.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "task_type": task_type.value,
            "role_group": role.value,
            "assigned_to": str(decision.user_id),
            "open_task_count_at_assignment": decision.open_task_count,
            "avg_response_hours": decision.avg_response_hours,
            "reason": decision.reason,
            "fallback_used": decision.fallback_used,
            "referral_id": str(referral_id) if referral_id else None,
            "intern_id": str(intern_id) if intern_id else None,
            "sla_deadline": sla_deadline.isoformat(),
            "routed_at": datetime.now(UTC).isoformat(),
        },
        session=session,
    )

    logger.info(
        "nexhire.ai.auto_router.routed",
        extra={
            "task_type": task_type.value,
            "role": role.value,
            "assigned_to": str(decision.user_id),
            "fallback_used": decision.fallback_used,
        },
    )
    return task


__all__ = [
    "MODEL_TOUCHPOINT",
    "RoutingDecision",
    "create_routed_task",
    "pick_assignee",
]
