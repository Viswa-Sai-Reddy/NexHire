"""Mentor picker API used by the referral form (Step 3 of the wizard).

S1 ships a basic list with capacity counts. AI-2 (ranked top-3 with
radar-chart scoring) lands in S2 alongside the auto-approval engine.

GET /mentors/eligible
  → mentors with `can_mentor=true`, sorted by name, with their current
    accepted-mentee count and the live threshold. The form filters out
    full mentors and excludes the requesting referrer (RULE-E3 hint).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.ai import mentor_matcher
from app.modules.ai import service as ai_service
from app.modules.auth.rbac import Permission, require
from app.modules.referral import service as referral_service
from app.modules.referral.models import MentorThresholdConfig
from app.modules.referral.schemas import (
    MentorPickerEntry,
    MentorPickerResponse,
    MentorRadar,
    MentorSuggestRequest,
    MentorSuggestResponse,
    MentorSuggestion,
)


picker_router = APIRouter(prefix="/mentors", tags=["mentors"])


@picker_router.get(
    "/eligible",
    response_model=MentorPickerResponse,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SUBMIT_REFERRAL)),
    ],
    summary="List mentors visible in the referral form picker.",
)
async def eligible(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MentorPickerResponse:
    threshold_row = (
        await session.execute(
            select(MentorThresholdConfig).where(
                MentorThresholdConfig.is_current.is_(True)
            )
        )
    ).scalar_one()
    threshold = threshold_row.max_mentees

    rows = await referral_service.list_eligible_mentors(
        session,
        threshold=threshold,
        exclude_user_id=principal.user_id,
    )

    return MentorPickerResponse(
        threshold=threshold,
        mentors=[
            MentorPickerEntry(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,  # type: ignore[arg-type]
                active_mentees=active,
                threshold=threshold,
                available=active < threshold,
            )
            for user, active in rows
        ],
    )


@picker_router.post(
    "/suggest",
    response_model=MentorSuggestResponse,
    dependencies=[
        Depends(rate_limit("ai")),
        Depends(require(Permission.SUBMIT_REFERRAL)),
    ],
    summary="AI-2: ranked top mentor suggestions with radar scores.",
)
async def suggest(
    body: MentorSuggestRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> MentorSuggestResponse:
    excluded = list(body.excluded_mentor_ids)
    # The form's referrer can never mentor their own candidate (RULE-E3).
    if principal.user_id not in excluded:
        excluded.append(principal.user_id)

    recs = await ai_service.suggest_mentors_and_persist(
        session,
        referral_id=None,  # call happens before referral row exists
        input_=mentor_matcher.MatchInput(
            candidate_skills=body.candidate_skills,
            college_id=body.college_id,
            excluded_mentor_ids=excluded,
        ),
        top_n=body.top_n,
    )

    threshold = recs[0].threshold if recs else 0
    return MentorSuggestResponse(
        threshold=threshold,
        suggestions=[
            MentorSuggestion(
                user_id=r.user_id,
                full_name=r.full_name,
                email=r.email,  # type: ignore[arg-type]
                active_mentees=r.active_mentees,
                threshold=r.threshold,
                match_score=r.match_score,
                radar=MentorRadar(**r.radar.to_dict()),
                reason=r.reason,
                ai_reason=r.ai_reason,
            )
            for r in recs
        ],
    )
