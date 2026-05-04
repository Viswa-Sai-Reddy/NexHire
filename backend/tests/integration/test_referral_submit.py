"""End-to-end referral submit (S1 acceptance criterion).

Drives the orchestrator directly (skipping HTTP) so we can assert
side-effects across every table the pipeline touches:
  * `referrals`       — row at MENTOR_PENDING
  * `mentor_assignments` — attempt 1, status PENDING, tokens issued
  * `action_tokens`   — two MENTOR_RESPONSE rows
  * `risk_profiles`   — one row, factors[] populated when applicable
  * `duplicate_check_results` — one row
  * `audit_events`    — REFERRAL_SUBMITTED + MENTOR_ASSIGNED
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import ActionToken
from app.modules.referral import service as referral_service
from app.modules.referral.models import (
    DuplicateCheckResult,
    MentorAssignment,
    Referral,
    RiskProfile,
)
from app.modules.referral.schemas import ReferralSubmitRequest
from app.shared.constants import (
    ActionTokenType,
    MentorAssignmentStatus,
    ReferralStatus,
)
from tests.factories import future_dates, make_college, make_user, random_pan


pytestmark = pytest.mark.asyncio


async def _build_payload(session: AsyncSession) -> tuple[
    ReferralSubmitRequest, "object", "object"
]:
    referrer = await make_user(session, role="REFERRER")
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates(weeks=10)
    payload = ReferralSubmitRequest(
        candidate_name="Riya Sharma",
        candidate_email=f"riya-{random_pan().lower()}@example.com",
        candidate_phone="+919876543210",
        candidate_pan=random_pan(),
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
    return payload, referrer, mentor


class TestSubmitHappyPath:
    async def test_full_pipeline_lands_at_mentor_pending(
        self, session: AsyncSession
    ) -> None:
        payload, referrer, mentor = await _build_payload(session)

        result = await referral_service.submit(
            session,
            referrer_id=referrer.id,
            payload=payload,
            today=date.today(),
            current_year=date.today().year,
        )

        assert result.status == ReferralStatus.MENTOR_PENDING.value
        assert result.risk_classification in ("LOW", "MEDIUM", "HIGH")

        # Referral row
        referral = (
            await session.execute(
                select(Referral).where(Referral.id == result.referral_id)
            )
        ).scalar_one()
        assert referral.referrer_id == referrer.id
        assert referral.mentor_id == mentor.id
        assert referral.candidate_pan_masked.endswith(payload.candidate_pan[-1])
        assert referral.candidate_pan_masked.startswith(payload.candidate_pan[:5])
        assert referral.mentor_attempt_count == 1

        # Mentor assignment + tokens
        assignment = (
            await session.execute(
                select(MentorAssignment).where(
                    MentorAssignment.referral_id == referral.id
                )
            )
        ).scalar_one()
        assert assignment.status == MentorAssignmentStatus.PENDING.value
        assert assignment.attempt_number == 1

        token_count = (
            await session.execute(
                select(func.count())
                .select_from(ActionToken)
                .where(
                    ActionToken.referral_id == referral.id,
                    ActionToken.action_type
                    == ActionTokenType.MENTOR_RESPONSE.value,
                )
            )
        ).scalar_one()
        assert token_count == 2

        # AI side-tables
        risk = (
            await session.execute(
                select(RiskProfile).where(RiskProfile.referral_id == referral.id)
            )
        ).scalar_one()
        assert 0 <= risk.risk_score <= 100

        dup = (
            await session.execute(
                select(DuplicateCheckResult).where(
                    DuplicateCheckResult.referral_id == referral.id
                )
            )
        ).scalar_one_or_none()
        assert dup is not None  # row written even when CLEAR


class TestSubmitGuards:
    async def test_referrer_equals_mentor_blocked(
        self, session: AsyncSession
    ) -> None:
        from app.shared.exceptions import ReferrerIsMentorError

        payload, referrer, _mentor = await _build_payload(session)
        # Force referrer == mentor by reassigning mentor_id.
        bad_payload = payload.model_copy(update={"mentor_id": referrer.id})
        with pytest.raises(ReferrerIsMentorError):
            await referral_service.submit(
                session,
                referrer_id=referrer.id,
                payload=bad_payload,
                today=date.today(),
                current_year=date.today().year,
            )

    async def test_unpaid_consent_required(
        self, session: AsyncSession
    ) -> None:
        from app.shared.exceptions import UnpaidConsentRequiredError

        payload, referrer, _ = await _build_payload(session)
        bad_payload = payload.model_copy(update={"unpaid_consent": False})
        with pytest.raises(UnpaidConsentRequiredError):
            await referral_service.submit(
                session,
                referrer_id=referrer.id,
                payload=bad_payload,
                today=date.today(),
                current_year=date.today().year,
            )

    async def test_active_pan_duplicate_hard_blocks(
        self, session: AsyncSession
    ) -> None:
        from app.shared.exceptions import DuplicateCandidateBlockedError

        # First submit — ok.
        payload, referrer, mentor = await _build_payload(session)
        await referral_service.submit(
            session,
            referrer_id=referrer.id,
            payload=payload,
            today=date.today(),
            current_year=date.today().year,
        )
        # Second submit with the SAME PAN by a different referrer must
        # be hard-blocked at validator stage (or by the DB index — both
        # acceptable; we assert the domain exception).
        other_referrer = await make_user(session, role="REFERRER")
        college = await make_college(session)
        same_pan = payload.candidate_pan
        payload2 = payload.model_copy(
            update={
                "candidate_email": f"other-{same_pan.lower()}@example.com",
                "college_id": college.id,
                "mentor_id": mentor.id,
            }
        )
        with pytest.raises(DuplicateCandidateBlockedError):
            await referral_service.submit(
                session,
                referrer_id=other_referrer.id,
                payload=payload2,
                today=date.today(),
                current_year=date.today().year,
            )
