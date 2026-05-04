"""Hourly SLA breach scanner.

Finds open tasks past `sla_deadline`, marks `warned_at` / `escalated_at`,
and writes audit events. Notification fan-out is left to S6.x extensions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_hourly,
    idempotent_job,
    register_interval_job,
)
from app.middleware import audit
from app.modules.referral.models import Task
from app.shared.constants import AI_SYSTEM_USER_ID, TaskStatus

logger = logging.getLogger("nexhire.workflow.sla_breach")


@idempotent_job(
    "sla_breach_hourly",
    bucket=bucket_hourly,
    lock_ttl_seconds=3_600,
)
async def scan_sla_breaches() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        now = datetime.now(timezone.utc)
        rows = (
            await session.execute(
                select(Task).where(
                    Task.status.notin_(
                        (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value)
                    ),
                    Task.sla_deadline < now,
                )
            )
        ).scalars().all()
        for task in rows:
            hours_overdue = int((now - task.sla_deadline).total_seconds() // 3_600)
            if task.warned_at is None:
                task.warned_at = now
            if hours_overdue >= 4 and task.escalated_at is None:
                task.escalated_at = now
                await audit.publish(
                    event_type="SLA_BREACH_ESCALATED",
                    entity_type="TASK",
                    entity_id=task.id,
                    actor_user_id=AI_SYSTEM_USER_ID,
                    actor_role="SYSTEM",
                    payload={
                        "task_type": task.task_type,
                        "hours_overdue": hours_overdue,
                        "assigned_to": str(task.assigned_to),
                    },
                    session=session,
                )


def register() -> None:
    register_interval_job("sla_breach_hourly", scan_sla_breaches, hours=1)
