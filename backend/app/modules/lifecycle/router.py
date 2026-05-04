"""Mentor S20 lifecycle endpoints + candidate termination self-service."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.auth.rbac import Permission, require
from app.modules.lifecycle import service


lifecycle_router = APIRouter(prefix="/interns", tags=["lifecycle"])


class ConfirmStartRequest(BaseModel):
    intern_id: UUID


class ExtensionRequest(BaseModel):
    intern_id: UUID
    new_end_date: date
    reason: str = Field(..., min_length=10, max_length=2000)


class CompletionRequest(BaseModel):
    intern_id: UUID
    project_summary: str = Field(..., min_length=10, max_length=200)
    skills_demonstrated: list[str] = Field(default_factory=list)
    recommendation_strength: int = Field(..., ge=1, le=5)
    notable_contributions: str | None = Field(None, max_length=500)


class TerminationRequest(BaseModel):
    intern_id: UUID
    reason: str = Field(..., min_length=10, max_length=2000)


@lifecycle_router.post(
    "/confirm-start",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.ACCEPT_REJECT_MENTORING)),
    ],
)
async def confirm_start_endpoint(
    body: ConfirmStartRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    intern = await service.confirm_start(
        session, intern_id=body.intern_id, mentor_user_id=principal.user_id
    )
    return {"status": intern.status, "actual_start_date": intern.actual_start_date}


@lifecycle_router.post(
    "/extend",
    dependencies=[
        Depends(rate_limit("default")),
    ],
)
async def extend_endpoint(
    body: ExtensionRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    intern = await service.request_extension(
        session,
        intern_id=body.intern_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        new_end_date=body.new_end_date,
        reason=body.reason,
    )
    return {
        "status": intern.status,
        "new_end_date": intern.actual_end_date,
        "extension_count": intern.extension_count,
    }


@lifecycle_router.post(
    "/confirm-completion",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.ACCEPT_REJECT_MENTORING)),
    ],
)
async def confirm_completion_endpoint(
    body: CompletionRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    feedback: dict[str, Any] = {
        "project_summary": body.project_summary,
        "skills_demonstrated": body.skills_demonstrated,
        "recommendation_strength": body.recommendation_strength,
        "notable_contributions": body.notable_contributions or "",
    }
    intern = await service.confirm_completion(
        session,
        intern_id=body.intern_id,
        mentor_user_id=principal.user_id,
        feedback=feedback,
    )
    return {"status": intern.status}


@lifecycle_router.post(
    "/terminate",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.INITIATE_TERMINATION)),
    ],
)
async def terminate_endpoint(
    body: TerminationRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    intern = await service.terminate(
        session,
        intern_id=body.intern_id,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        reason=body.reason,
    )
    return {"status": intern.status}
