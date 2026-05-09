"""IT/AD + Admin task queue endpoints (S21/S22 backend)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.access import service
from app.modules.auth.rbac import Permission, require
from app.modules.referral.models import Task
from app.shared.constants import (
    TaskStatus,
    UserRole,
)

access_router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskQueueEntry(BaseModel):
    id: UUID
    task_type: str
    intern_id: UUID | None
    referral_id: UUID | None
    sla_deadline: datetime
    status: str
    ai_routing_reason: str | None
    created_at: datetime


class TaskQueueResponse(BaseModel):
    items: list[TaskQueueEntry]


class CompleteAdRequest(BaseModel):
    intern_id: UUID


class CompleteBadgeRequest(BaseModel):
    intern_id: UUID
    badge_reference: str = Field(..., min_length=2, max_length=255)


@access_router.get(
    "/mine",
    response_model=TaskQueueResponse,
    summary="Open tasks routed to the calling user.",
)
async def my_tasks(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> TaskQueueResponse:
    rows = (
        await session.execute(
            select(Task)
            .where(
                Task.assigned_to == principal.user_id,
                Task.status.notin_(
                    (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value)
                ),
            )
            .order_by(Task.sla_deadline.asc())
        )
    ).scalars().all()
    return TaskQueueResponse(
        items=[
            TaskQueueEntry(
                id=t.id,
                task_type=t.task_type,
                intern_id=t.intern_id,
                referral_id=t.referral_id,
                sla_deadline=t.sla_deadline,
                status=t.status,
                ai_routing_reason=t.ai_routing_reason,
                created_at=t.created_at,
            )
            for t in rows
        ]
    )


@access_router.post(
    "/ad-provision/complete",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.PROVISION_AD_ACCOUNT)),
    ],
    summary="IT marks AD provisioning complete (calls Graph).",
)
async def complete_ad(
    body: CompleteAdRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Literal["ok"]]:
    await service.complete_ad_provisioning(
        session,
        intern_id=body.intern_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
    )
    return {"status": "ok"}


@access_router.post(
    "/badge-access/complete",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.MANAGE_BADGE_ACCESS)),
    ],
    summary="Admin marks badge access configured.",
)
async def complete_badge(
    body: CompleteBadgeRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Literal["ok"]]:
    await service.complete_badge_access(
        session,
        intern_id=body.intern_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        badge_reference=body.badge_reference,
    )
    return {"status": "ok"}


# Suppress unused-import warning when the file is loaded standalone.
_ = UserRole
