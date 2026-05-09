"""F-35 auto-approval engine — mentor-accept always auto-approves; flags
are recorded for audit but do not divert the referral to HR.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral import service as referral_service
from app.modules.referral.models import (
    AiAutoAction,
    AiParseResult,
    DuplicateCheckResult,
    Referral,
    RiskProfile,
    Task,
)
from app.modules.referral.schemas import ReferralSubmitRequest
from app.modules.workflow import auto_approval
from app.shared.constants import (
    ReferralStatus,
    TaskType,
)
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _seeded_referral(session: AsyncSession) -> tuple[Referral, str]:
    """Submit a clean referral end-to-end, then return its row + mentor id."""
    referrer = await make_user(session, role="REFERRER")
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates(weeks=10)
    pan = random_pan()
    payload = ReferralSubmitRequest(
        candidate_name="Riya Sharma",
        candidate_email=f"riya-{pan.lower()}@example.com",
        candidate_phone="+919876543210",
        candidate_pan=pan,
        college_id=college.id,
        candidate_year_of_study=3,
        candidate_graduation_year=2027,
        unpaid_consent=True,
        inperson_ready=True,
        relationship_declaration="None",
        relationship_declaration_detail=None,
        mentor_id=mentor.id,
        project_title="ML Pipeline Optimization",
        project_overview="Improve throughput on the inference pipeline",
        joining_location="Bangalore",
        internship_start_date=start,
        internship_end_date=end,
        resume_document_id=None,
    )
    result = await referral_service.submit(
        session,
        referrer_id=referrer.id,
        payload=payload,
        today=date.today(),
        current_year=date.today().year,
    )
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == result.referral_id)
        )
    ).scalar_one()
    return referral, str(mentor.id)


class TestAutoApprovalCleanCase:
    async def test_clean_referral_auto_approved(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)

        # Pre-conditions for clean case: no AI parse row (so no
        # confidence flag), no resume red flags, low risk score (no
        # distance flagged because joining_location.state isn't set
        # in the factory). The submission already wrote a fuzzy-dup
        # row with score=0.0 (no prior referrals exist).
        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )

        assert result.decision == "AUTO_APPROVED"
        await session.refresh(referral)
        assert referral.status == ReferralStatus.APPROVED.value
        assert referral.approved_by_label == "AI_AUTO_APPROVAL"

        action = (
            await session.execute(
                select(AiAutoAction).where(AiAutoAction.referral_id == referral.id)
            )
        ).scalar_one()
        assert action.action_type == "AUTO_APPROVE"
        assert action.decision == "EXECUTED"


class TestAutoApprovalFlaggedCase:
    """Flagged cases still auto-approve; flags land on `ai_auto_actions`
    so HR can recall within the 2-hour window if needed.
    """

    async def test_high_risk_still_auto_approved(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        risk = (
            await session.execute(
                select(RiskProfile).where(RiskProfile.referral_id == referral.id)
            )
        ).scalar_one()
        risk.risk_score = 50
        await session.flush()

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )

        assert result.decision == "AUTO_APPROVED"
        assert any("Risk score" in f for f in result.flags)

        await session.refresh(referral)
        assert referral.status == ReferralStatus.APPROVED.value
        assert referral.approved_by_label == "AI_AUTO_APPROVAL"

        action = (
            await session.execute(
                select(AiAutoAction).where(AiAutoAction.referral_id == referral.id)
            )
        ).scalar_one()
        assert action.decision == "EXECUTED"
        assert action.flags is not None
        assert any("Risk score" in f for f in action.flags)

        # No HR_REVIEW task should be created.
        hr_task = (
            await session.execute(
                select(Task).where(
                    Task.referral_id == referral.id,
                    Task.task_type == TaskType.HR_REVIEW.value,
                )
            )
        ).scalar_one_or_none()
        assert hr_task is None

    async def test_pan_match_still_auto_approved(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        dup = (
            await session.execute(
                select(DuplicateCheckResult).where(
                    DuplicateCheckResult.referral_id == referral.id
                )
            )
        ).scalar_one()
        dup.match_type = "PAN_EXACT"
        dup.similarity_score = 1.0
        await session.flush()

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )

        assert result.decision == "AUTO_APPROVED"
        assert any("PAN duplicate" in f for f in result.flags)

        action = (
            await session.execute(
                select(AiAutoAction).where(AiAutoAction.referral_id == referral.id)
            )
        ).scalar_one()
        assert action.decision == "EXECUTED"
        assert action.flags is not None
        assert any("PAN duplicate" in f for f in action.flags)

    async def test_low_confidence_still_auto_approved(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        session.add(
            AiParseResult(
                ai_touchpoint="RESUME_PARSE",
                model_version="test:v1",
                raw_output={"red_flags": []},
                referral_id=referral.id,
                confidence_scores={"phone": 0.7, "email": 0.95},
                succeeded=True,
            )
        )
        await session.flush()

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )
        assert result.decision == "AUTO_APPROVED"
        assert any("Low confidence" in f for f in result.flags)
