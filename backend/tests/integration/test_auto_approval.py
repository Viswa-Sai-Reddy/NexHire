"""F-35 auto-approval engine — clean → APPROVED, flagged → HR_REVIEW."""
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
    TaskStatus,
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
    async def test_high_risk_routes_to_hr_with_task(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        # Force a HIGH risk score by writing a RiskProfile row that
        # exceeds the 25-point threshold.
        risk = (
            await session.execute(
                select(RiskProfile).where(RiskProfile.referral_id == referral.id)
            )
        ).scalar_one()
        risk.risk_score = 50
        await session.flush()

        # Need at least one HR user so AI-10 can route the task.
        await make_user(session, role="HR")

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )

        assert result.decision == "ROUTED_TO_HR"
        assert any("Risk score" in f for f in result.flags)

        await session.refresh(referral)
        assert referral.status == ReferralStatus.HR_REVIEW.value

        # An HR_REVIEW task was created.
        task = (
            await session.execute(
                select(Task)
                .where(
                    Task.referral_id == referral.id,
                    Task.task_type == TaskType.HR_REVIEW.value,
                )
                .limit(1)
            )
        ).scalar_one()
        assert task.status == TaskStatus.PENDING.value
        assert task.assigned_by_ai is True

    async def test_pan_match_hard_blocks_with_likely_reject(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        # Manually flip the duplicate-check row to PAN_EXACT.
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

        await make_user(session, role="HR")

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )

        assert result.decision == "ROUTED_TO_HR"
        assert result.hr_recommendation == "LIKELY_REJECT"

        action = (
            await session.execute(
                select(AiAutoAction).where(AiAutoAction.referral_id == referral.id)
            )
        ).scalar_one()
        assert action.decision == "HARD_BLOCK"

    async def test_low_confidence_only_likely_approve(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seeded_referral(session)
        # Write a low-confidence parse row.
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

        await make_user(session, role="HR")

        result = await auto_approval.evaluate_and_route(
            session, referral_id=referral.id
        )
        assert result.decision == "ROUTED_TO_HR"
        assert result.hr_recommendation == "LIKELY_APPROVE"
        assert any("Low confidence" in f for f in result.flags)
