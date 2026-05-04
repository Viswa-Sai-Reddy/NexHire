"""HR review endpoints (S2.6) — /referrals/hr/*.

Visible only to HR + PO. Backed by `app.modules.workflow.hr_service`
(business logic) and `app.modules.workflow.recall` (AUTO_APPROVE recall).

Endpoints:
  GET  /referrals/hr/queue         — flagged referrals awaiting review
  GET  /referrals/hr/recent-ai     — recent AI auto-actions (recall list)
  POST /referrals/hr/{id}/approve         — HR_REVIEW → APPROVED
  POST /referrals/hr/{id}/reject          — HR_REVIEW → HR_REJECTED
  POST /referrals/hr/{id}/request-correction
                                   — HR_REVIEW → CORRECTION_NEEDED
  POST /referrals/hr/{id}/recall   — undo a recent AUTO_APPROVE (≤2h)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.auth.rbac import Permission, require
from app.modules.referral import repository
from app.modules.referral.models import (
    AiAutoAction,
    AiParseResult,
    DuplicateCheckResult,
    Referral,
    RiskProfile,
    Task,
)
from app.modules.mentor import service as mentor_service
from app.modules.referral.schemas import ReferralDetail, ReferralSummary
from app.modules.workflow import hr_service, recall
from app.shared.constants import (
    ReferralStatus,
    TaskStatus,
    TaskType,
)


logger = logging.getLogger("nexhire.router.hr")

hr_router = APIRouter(prefix="/referrals/hr", tags=["referrals-hr"])


# ────────────────────────────────────────────────────────────────────
# Request/response schemas (HR-specific; not part of the public form
# surface so they live here rather than in referral/schemas.py).
# ────────────────────────────────────────────────────────────────────
class HrApproveRequest(BaseModel):
    notes: str | None = Field(None, max_length=2000)


class HrRejectRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


class HrCorrectionRequest(BaseModel):
    notes: str = Field(..., min_length=10, max_length=2000)


class HrRecallRequest(BaseModel):
    reason: str | None = Field(None, max_length=2000)


class HrReassignMentorRequest(BaseModel):
    new_mentor_id: UUID
    reason: str = Field(..., min_length=10, max_length=2000)


class HrQueueEntry(ReferralSummary):
    flags: list[str] = Field(default_factory=list)
    hr_recommendation: str | None = None
    auto_action_id: UUID | None = None
    routed_at: datetime | None = None


class HrQueueResponse(BaseModel):
    total: int
    items: list[HrQueueEntry]


class RecentAiActionEntry(BaseModel):
    auto_action_id: UUID
    referral_id: UUID
    action_type: str
    decision: str
    executed_at: datetime
    recall_window_ends_at: datetime
    recall_active: bool


class RecentAiActionsResponse(BaseModel):
    items: list[RecentAiActionEntry]


class HrReviewContext(BaseModel):
    """Full context the HR Review Panel (S12) renders for one referral."""

    referral: ReferralDetail
    risk_score: int | None = None
    risk_classification: str | None = None
    risk_factors: list[dict] = Field(default_factory=list)
    risk_narrative: str | None = None
    duplicate_recommendation: str | None = None
    duplicate_similarity: float | None = None
    duplicate_match_reasons: list[str] = Field(default_factory=list)
    duplicate_matched_referral_id: UUID | None = None
    resume_skills: list[str] = Field(default_factory=list)
    resume_red_flags: list[str] = Field(default_factory=list)
    resume_recommended_questions: list[str] = Field(default_factory=list)
    resume_internship_readiness: int | None = None
    auto_action_id: UUID | None = None
    auto_action_decision: str | None = None
    auto_action_flags: list[str] = Field(default_factory=list)
    auto_action_recommendation: str | None = None
    auto_action_executed_at: datetime | None = None
    recall_window_ends_at: datetime | None = None
    recall_active: bool = False


# ────────────────────────────────────────────────────────────────────
# Reads.
# ────────────────────────────────────────────────────────────────────
@hr_router.get(
    "/queue",
    response_model=HrQueueResponse,
    dependencies=[Depends(require(Permission.APPROVE_REJECT_REFERRAL))],
    summary="Flagged referrals waiting on HR review.",
)
async def hr_queue(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> HrQueueResponse:
    rows = (
        await session.execute(
            select(Referral, AiAutoAction)
            .join(
                AiAutoAction,
                (AiAutoAction.referral_id == Referral.id)
                & (AiAutoAction.action_type == "AUTO_APPROVE"),
                isouter=True,
            )
            .where(Referral.status == ReferralStatus.HR_REVIEW.value)
            .order_by(Referral.stage_entered_at.asc())
            .limit(limit)
        )
    ).all()

    items: list[HrQueueEntry] = []
    for referral, action in rows:
        flags = list(action.flags) if action and action.flags else []
        recommendation = action.hr_recommendation if action else None
        items.append(
            HrQueueEntry(
                **_referral_summary_dict(referral),
                flags=[str(f) for f in flags],
                hr_recommendation=recommendation,
                auto_action_id=action.id if action else None,
                routed_at=action.executed_at if action else None,
            )
        )
    return HrQueueResponse(total=len(items), items=items)


@hr_router.get(
    "/recent-ai",
    response_model=RecentAiActionsResponse,
    dependencies=[Depends(require(Permission.RECALL_AI_AUTO_ACTION))],
    summary="Recent AI auto-actions still inside their recall window.",
)
async def recent_ai_actions(
    session: AsyncSession = Depends(get_session),
) -> RecentAiActionsResponse:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(recall.RECALL_HOURS.values()) + 1)
    rows = (
        await session.execute(
            select(AiAutoAction)
            .where(
                AiAutoAction.executed_at >= cutoff,
                AiAutoAction.recalled_at.is_(None),
                AiAutoAction.decision == "EXECUTED",
            )
            .order_by(AiAutoAction.executed_at.desc())
            .limit(100)
        )
    ).scalars().all()

    items: list[RecentAiActionEntry] = []
    for row in rows:
        window_hours = recall.RECALL_HOURS.get(row.action_type, 0)
        ends_at = row.executed_at + timedelta(hours=window_hours)
        items.append(
            RecentAiActionEntry(
                auto_action_id=row.id,
                referral_id=row.referral_id,  # type: ignore[arg-type]
                action_type=row.action_type,
                decision=row.decision,
                executed_at=row.executed_at,
                recall_window_ends_at=ends_at,
                recall_active=ends_at > now,
            )
        )
    return RecentAiActionsResponse(items=items)


# ────────────────────────────────────────────────────────────────────
# Mutations.
# ────────────────────────────────────────────────────────────────────
@hr_router.get(
    "/{referral_id}/review",
    response_model=HrReviewContext,
    dependencies=[Depends(require(Permission.APPROVE_REJECT_REFERRAL))],
    summary="Full review context: referral + risk + dedup + resume + auto-action.",
)
async def review_context(
    referral_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> HrReviewContext:
    referral = await repository.get(session, referral_id)
    if referral is None:
        from app.shared.exceptions import BusinessRuleError

        raise BusinessRuleError(
            user_message="Referral not found.",
            details={"referral_id": str(referral_id)},
        )

    risk = (
        await session.execute(
            select(RiskProfile).where(RiskProfile.referral_id == referral.id)
        )
    ).scalar_one_or_none()

    duplicate = (
        await session.execute(
            select(DuplicateCheckResult)
            .where(DuplicateCheckResult.referral_id == referral.id)
            .order_by(DuplicateCheckResult.checked_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    resume_parse = (
        await session.execute(
            select(AiParseResult)
            .where(
                AiParseResult.referral_id == referral.id,
                AiParseResult.ai_touchpoint == "RESUME_PARSE",
            )
            .order_by(AiParseResult.parsed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    auto_action = (
        await session.execute(
            select(AiAutoAction)
            .where(
                AiAutoAction.referral_id == referral.id,
                AiAutoAction.action_type == "AUTO_APPROVE",
            )
            .order_by(AiAutoAction.executed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    detail = ReferralDetail(
        **_referral_summary_dict(referral),
        candidate_phone=referral.candidate_phone,
        candidate_year_of_study=referral.candidate_year_of_study,
        candidate_graduation_year=referral.candidate_graduation_year,
        project_overview=referral.project_overview,
        joining_location=referral.joining_location,
        internship_start_date=referral.internship_start_date,
        internship_end_date=referral.internship_end_date,
        rejection_reason=referral.rejection_reason,
    )

    raw_resume = (
        resume_parse.raw_output if resume_parse and isinstance(resume_parse.raw_output, dict) else {}
    )

    risk_classification = _classify_risk(risk.risk_score) if risk else None

    now = datetime.now(timezone.utc)
    recall_ends = None
    recall_active = False
    if auto_action is not None and auto_action.action_type in recall.RECALL_HOURS:
        recall_ends = auto_action.executed_at + timedelta(
            hours=recall.RECALL_HOURS[auto_action.action_type]
        )
        recall_active = (
            auto_action.recalled_at is None
            and auto_action.decision == "EXECUTED"
            and recall_ends > now
        )

    return HrReviewContext(
        referral=detail,
        risk_score=risk.risk_score if risk else None,
        risk_classification=risk_classification,
        risk_factors=list(risk.factors or []) if risk else [],
        risk_narrative=risk.narrative if risk else None,
        duplicate_recommendation=duplicate.recommendation if duplicate else None,
        duplicate_similarity=duplicate.similarity_score if duplicate else None,
        duplicate_match_reasons=[str(r) for r in (duplicate.match_reasons or [])]
        if duplicate
        else [],
        duplicate_matched_referral_id=duplicate.matched_referral_id if duplicate else None,
        resume_skills=[str(s) for s in raw_resume.get("skills", [])],
        resume_red_flags=[str(f) for f in raw_resume.get("red_flags", [])],
        resume_recommended_questions=[
            str(q) for q in raw_resume.get("recommended_mentor_questions", [])
        ],
        resume_internship_readiness=raw_resume.get("internship_readiness_score"),
        auto_action_id=auto_action.id if auto_action else None,
        auto_action_decision=auto_action.decision if auto_action else None,
        auto_action_flags=[str(f) for f in (auto_action.flags or [])]
        if auto_action
        else [],
        auto_action_recommendation=auto_action.hr_recommendation if auto_action else None,
        auto_action_executed_at=auto_action.executed_at if auto_action else None,
        recall_window_ends_at=recall_ends,
        recall_active=recall_active,
    )


def _classify_risk(score: int) -> str:
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "MEDIUM"
    return "HIGH"


@hr_router.post(
    "/{referral_id}/approve",
    response_model=ReferralSummary,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.APPROVE_REJECT_REFERRAL)),
    ],
)
async def approve_endpoint(
    referral_id: UUID,
    body: HrApproveRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSummary:
    referral = await hr_service.approve(
        session,
        referral_id=referral_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role,
        notes=body.notes,
    )
    return ReferralSummary(**_referral_summary_dict(referral))


@hr_router.post(
    "/{referral_id}/reject",
    response_model=ReferralSummary,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.APPROVE_REJECT_REFERRAL)),
    ],
)
async def reject_endpoint(
    referral_id: UUID,
    body: HrRejectRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSummary:
    referral = await hr_service.reject(
        session,
        referral_id=referral_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role,
        reason=body.reason,
    )
    return ReferralSummary(**_referral_summary_dict(referral))


@hr_router.post(
    "/{referral_id}/request-correction",
    response_model=ReferralSummary,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.APPROVE_REJECT_REFERRAL)),
    ],
)
async def correction_endpoint(
    referral_id: UUID,
    body: HrCorrectionRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSummary:
    referral = await hr_service.request_correction(
        session,
        referral_id=referral_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role,
        notes=body.notes,
    )
    return ReferralSummary(**_referral_summary_dict(referral))


@hr_router.post(
    "/{referral_id}/reassign-mentor",
    response_model=ReferralSummary,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.REASSIGN_MENTOR)),
    ],
    summary="A14: HR mid-flow mentor reassignment without strike-counter cost.",
)
async def reassign_mentor_endpoint(
    referral_id: UUID,
    body: HrReassignMentorRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSummary:
    await mentor_service.reassign_by_hr(
        session,
        referral_id=referral_id,
        new_mentor_id=body.new_mentor_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role.value,
        reason=body.reason,
    )
    referral = await repository.get(session, referral_id)
    assert referral is not None  # just mutated above
    return ReferralSummary(**_referral_summary_dict(referral))


@hr_router.post(
    "/{referral_id}/recall",
    response_model=ReferralSummary,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.RECALL_AI_AUTO_ACTION)),
    ],
    summary="Recall a recent AUTO_APPROVE (within the 2h window).",
)
async def recall_endpoint(
    referral_id: UUID,
    body: HrRecallRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSummary:
    referral = await recall.recall_auto_approve(
        session,
        referral_id=referral_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role,
        reason=body.reason,
    )
    return ReferralSummary(**_referral_summary_dict(referral))


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
def _referral_summary_dict(r: Referral) -> dict:
    return {
        "id": r.id,
        "status": r.status,
        "current_stage": r.current_stage,
        "candidate_name": r.candidate_name,
        "candidate_email": r.candidate_email,
        "pan_masked": r.candidate_pan_masked,
        "college_id": r.college_id,
        "project_title": r.project_title,
        "submitted_at": r.submitted_at,
        "mentor_id": r.mentor_id,
        "mentor_attempt_count": r.mentor_attempt_count,
        "created_at": r.created_at,
    }


# Suppress unused-import warnings.
_ = Optional, Task, TaskStatus, TaskType, repository
