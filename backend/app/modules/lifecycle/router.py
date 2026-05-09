"""Mentor S20 lifecycle endpoints + candidate termination self-service."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.ai import certificate as ai_certificate
from app.modules.auth.rbac import Permission, require
from app.modules.lifecycle import service
from app.modules.mentor import service as mentor_service

lifecycle_router = APIRouter(prefix="/interns", tags=["lifecycle"])


class MentorInternEntry(BaseModel):
    # `intern_id` and intern-specific fields are None until HR approves
    # and an Intern row is created. The mentor still sees the row so
    # they know what's in the pipeline.
    intern_id: UUID | None
    referral_id: UUID
    candidate_name: str
    candidate_email: str
    referral_status: str
    intern_status: str | None
    project_title: str | None
    actual_start_date: date | None
    actual_end_date: date | None
    extension_count: int
    internship_start_date: date | None
    internship_end_date: date | None
    submitted_at: datetime | None
    # AI context surfaced for the dashboard accept/reject decision.
    risk_score: int | None
    red_flags: list[str]
    # True when a resume is attached — UI shows a "View resume" link.
    has_resume: bool


class MentorInternsResponse(BaseModel):
    items: list[MentorInternEntry]


class MentorRespondRequest(BaseModel):
    referral_id: UUID
    action: Literal["ACCEPT", "REJECT"]
    # Reason validation lives in the service for REJECT (the existing
    # `MentorRejectionReasonMissingError` enforces min length). Keeping
    # only an upper bound here so ACCEPT requests without a reason
    # don't trip a min-length check.
    reason: str | None = Field(default=None, max_length=2000)


class MentorRespondResponse(BaseModel):
    referral_id: UUID
    assignment_status: str
    referral_status: str
    is_terminal: bool


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


@lifecycle_router.get(
    "/mine",
    response_model=MentorInternsResponse,
    dependencies=[Depends(require(Permission.ACCEPT_REJECT_MENTORING))],
    summary="List interns where the caller is the assigned mentor.",
)
async def my_interns(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MentorInternsResponse:
    rows = await service.list_for_mentor(session, mentor_user_id=principal.user_id)
    items = [
        MentorInternEntry(
            intern_id=intern.id if intern else None,
            referral_id=referral.id,
            candidate_name=referral.candidate_name,
            candidate_email=referral.candidate_email,
            referral_status=referral.status,
            intern_status=intern.status if intern else None,
            project_title=referral.project_title,
            actual_start_date=intern.actual_start_date if intern else None,
            actual_end_date=intern.actual_end_date if intern else None,
            extension_count=intern.extension_count if intern else 0,
            internship_start_date=referral.internship_start_date,
            internship_end_date=referral.internship_end_date,
            submitted_at=referral.submitted_at,
            risk_score=risk_score,
            red_flags=red_flags,
            has_resume=referral.resume_document_id is not None,
        )
        for intern, referral, risk_score, red_flags in rows
    ]
    return MentorInternsResponse(items=items)


@lifecycle_router.post(
    "/respond",
    response_model=MentorRespondResponse,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.ACCEPT_REJECT_MENTORING)),
    ],
    summary="Mentor accepts or rejects an assignment from the dashboard.",
)
async def respond(
    body: MentorRespondRequest,
    principal: CurrentUser,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MentorRespondResponse:
    ip = request.client.host if request.client else None
    if body.action == "ACCEPT":
        assignment = await mentor_service.accept_by_mentor(
            session,
            referral_id=body.referral_id,
            mentor_user_id=principal.user_id,
            ip_address=ip,
        )
        is_terminal = False
    else:
        if not body.reason:
            from app.shared.exceptions import MentorRejectionReasonMissingError

            raise MentorRejectionReasonMissingError()
        assignment, is_terminal = await mentor_service.reject_by_mentor(
            session,
            referral_id=body.referral_id,
            mentor_user_id=principal.user_id,
            reason=body.reason,
            ip_address=ip,
        )

    # Fetch updated referral to report status back.
    from app.modules.referral.models import Referral

    referral = (
        await session.execute(select(Referral).where(Referral.id == body.referral_id))
    ).scalar_one()

    return MentorRespondResponse(
        referral_id=body.referral_id,
        assignment_status=assignment.status,
        referral_status=referral.status,
        is_terminal=is_terminal,
    )


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
    "/{intern_id}/generate-certificate",
    dependencies=[
        Depends(rate_limit("ai")),
        Depends(require(Permission.GENERATE_CERTIFICATE)),
    ],
    summary="HR/PO manually triggers AI-8 certificate generation for an intern.",
)
async def generate_certificate_endpoint(
    intern_id: UUID,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _ = principal  # presence-only — RBAC dep enforces GENERATE_CERTIFICATE
    auto_action = await ai_certificate.auto_send_for_intern(
        session, intern_id=intern_id
    )
    return {
        "auto_action_id": str(auto_action.id) if auto_action.id else None,
        "decision": auto_action.decision,
        "intern_id": str(intern_id),
    }


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
