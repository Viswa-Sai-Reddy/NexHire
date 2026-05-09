"""F-40 PAN decision tree — active duplicate, cooling, clear.

Exercises the real DB (testcontainers Postgres) so we cover:
  * The unique partial index `idx_referrals_active_pan` (Postgres
    won't even let a second active row land regardless of app logic).
  * The cooling-period query path against `referrals.cooling_*`.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral import pan_crypto, validator
from app.modules.referral.models import Referral
from app.shared.constants import ReferralStatus
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _seed_referral(
    session: AsyncSession,
    *,
    pan: str,
    status: str,
    cooling_months: int | None = None,
    cooling_end_offset_days: int | None = None,
) -> Referral:
    referrer = await make_user(session)
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates()

    cooling_start = None
    cooling_end = None
    if cooling_end_offset_days is not None:
        cooling_start = datetime.now(UTC)
        cooling_end = cooling_start + timedelta(days=cooling_end_offset_days)

    referral = Referral(
        referrer_id=referrer.id,
        mentor_id=mentor.id,
        candidate_name="Test Candidate",
        candidate_email=f"cand-{pan.lower()}@example.com",
        candidate_phone="+919999999999",
        college_id=college.id,
        candidate_year_of_study=3,
        candidate_graduation_year=2027,
        candidate_pan_hash=pan_crypto.hash_for_lookup(pan),
        candidate_pan_encrypted=pan_crypto.encrypt_for_display(pan),
        candidate_pan_masked=pan_crypto.mask(pan),
        project_title="Test Project",
        joining_location="Bangalore",
        internship_start_date=start,
        internship_end_date=end,
        unpaid_consent=True,
        inperson_ready=True,
        status=status,
        current_stage=status,
        cooling_period_months=cooling_months,
        cooling_period_start_at=cooling_start,
        cooling_period_end_at=cooling_end,
        cooling_triggered_by=status if cooling_months is not None else None,
    )
    session.add(referral)
    await session.flush()
    return referral


class TestPanDecisionTree:
    async def test_clear_when_no_prior_referral(
        self, session: AsyncSession
    ) -> None:
        result = await validator.pan_check(session, pan_plain=random_pan())
        assert result.verdict == "CLEAR"

    async def test_active_duplicate_hard_blocks(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        await _seed_referral(
            session, pan=pan, status=ReferralStatus.MENTOR_PENDING.value
        )
        result = await validator.pan_check(session, pan_plain=pan)
        assert result.verdict == "HARD_BLOCK"
        assert result.allow_override is False
        assert result.existing_referral_id is not None

    async def test_terminal_with_cooling_blocks(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        await _seed_referral(
            session,
            pan=pan,
            status=ReferralStatus.NDA_DECLINED_REJECTED.value,
            cooling_months=6,
            cooling_end_offset_days=120,
        )
        result = await validator.pan_check(session, pan_plain=pan)
        assert result.verdict == "COOLING_BLOCK"
        assert result.allow_override is True

    async def test_candidate_rejected_without_cooling_clears(
        self, session: AsyncSession
    ) -> None:
        # CANDIDATE_REJECTED has duration=0 — recorded for history,
        # never blocks (RULE-CP5).
        pan = random_pan()
        await _seed_referral(
            session,
            pan=pan,
            status=ReferralStatus.CANDIDATE_REJECTED.value,
            cooling_months=0,
            cooling_end_offset_days=0,
        )
        result = await validator.pan_check(session, pan_plain=pan)
        assert result.verdict == "CLEAR"

    async def test_elapsed_cooling_clears(self, session: AsyncSession) -> None:
        pan = random_pan()
        await _seed_referral(
            session,
            pan=pan,
            status=ReferralStatus.HR_REJECTED.value,
            cooling_months=3,
            cooling_end_offset_days=-1,  # ended yesterday
        )
        result = await validator.pan_check(session, pan_plain=pan)
        assert result.verdict == "CLEAR"
