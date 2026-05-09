"""CoolingPeriodService — apply, get_status, override (RULE-CP1..CP7)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral import cooling_period_service, pan_crypto
from app.modules.referral.models import Referral
from app.shared.constants import ReferralStatus, UserRole
from app.shared.exceptions import (
    InsufficientPermissionsError,
    OverrideReasonTooShortError,
)
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _persist_terminal_referral(
    session: AsyncSession,
    *,
    pan: str,
    status: str = ReferralStatus.NDA_DECLINED_REJECTED.value,
) -> Referral:
    referrer = await make_user(session)
    college = await make_college(session)
    start, end = future_dates()
    referral = Referral(
        referrer_id=referrer.id,
        candidate_name="X",
        candidate_email=f"x-{pan.lower()}@example.com",
        candidate_phone="+919998887776",
        college_id=college.id,
        candidate_year_of_study=3,
        candidate_graduation_year=2027,
        candidate_pan_hash=pan_crypto.hash_for_lookup(pan),
        candidate_pan_encrypted=pan_crypto.encrypt_for_display(pan),
        candidate_pan_masked=pan_crypto.mask(pan),
        joining_location="Bangalore",
        internship_start_date=start,
        internship_end_date=end,
        unpaid_consent=True,
        inperson_ready=True,
        project_title="X",
        status=status,
        current_stage=status,
    )
    session.add(referral)
    await session.flush()
    return referral


class TestApplyCoolingPeriod:
    async def test_nda_declined_writes_six_months(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(session, pan=pan)
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.NDA_DECLINED_REJECTED.value,
        )
        await session.refresh(referral)
        assert referral.cooling_period_months == 6
        assert referral.cooling_period_start_at is not None
        assert referral.cooling_period_end_at is not None
        # ~6 months later (give or take a day for relativedelta arithmetic).
        delta_days = (
            referral.cooling_period_end_at - referral.cooling_period_start_at
        ).days
        assert 175 <= delta_days <= 190

    async def test_candidate_rejected_zero_months_no_block(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(
            session, pan=pan, status=ReferralStatus.CANDIDATE_REJECTED.value
        )
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.CANDIDATE_REJECTED.value,
        )
        status = await cooling_period_service.get_status(
            session, pan_hash=referral.candidate_pan_hash
        )
        assert status.is_in_cooling is False


class TestOverride:
    async def test_program_owner_override_clears_cooling(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(session, pan=pan)
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.NDA_DECLINED_REJECTED.value,
        )
        po = await make_user(session, role=UserRole.PROGRAM_OWNER.value)
        await cooling_period_service.apply_override(
            session,
            referral_id=referral.id,
            program_owner_id=po.id,
            program_owner_role=UserRole.PROGRAM_OWNER,
            reason=(
                "Candidate had a verified medical emergency during the NDA "
                "period. HR confirmed via hospital documentation."
            ),
        )

        status = await cooling_period_service.get_status(
            session, pan_hash=referral.candidate_pan_hash
        )
        assert status.is_in_cooling is False
        assert status.override_applied is True

    async def test_non_po_blocked(self, session: AsyncSession) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(session, pan=pan)
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.NDA_DECLINED_REJECTED.value,
        )
        hr = await make_user(session, role=UserRole.HR.value)
        with pytest.raises(InsufficientPermissionsError):
            await cooling_period_service.apply_override(
                session,
                referral_id=referral.id,
                program_owner_id=hr.id,
                program_owner_role=UserRole.HR,  # not PO
                reason="Reasonable text long enough to clear the 50-char minimum guard",
            )

    async def test_short_reason_rejected(self, session: AsyncSession) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(session, pan=pan)
        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.NDA_DECLINED_REJECTED.value,
        )
        po = await make_user(session, role=UserRole.PROGRAM_OWNER.value)
        with pytest.raises(OverrideReasonTooShortError):
            await cooling_period_service.apply_override(
                session,
                referral_id=referral.id,
                program_owner_id=po.id,
                program_owner_role=UserRole.PROGRAM_OWNER,
                reason="too short",
            )


class TestGetStatus:
    async def test_no_referral_clears(self, session: AsyncSession) -> None:
        # Hash a never-seen PAN.
        result = await cooling_period_service.get_status(
            session, pan_hash=pan_crypto.hash_for_lookup(random_pan())
        )
        assert result.is_in_cooling is False

    async def test_active_cooling_reports_days(
        self, session: AsyncSession
    ) -> None:
        pan = random_pan()
        referral = await _persist_terminal_referral(session, pan=pan)
        # Pretend cooling was applied 10 days ago for 6 months.
        start = datetime.now(UTC) - timedelta(days=10)
        end = start + timedelta(days=180)
        referral.cooling_period_months = 6
        referral.cooling_period_start_at = start
        referral.cooling_period_end_at = end
        referral.cooling_triggered_by = (
            ReferralStatus.NDA_DECLINED_REJECTED.value
        )
        await session.flush()

        status = await cooling_period_service.get_status(
            session, pan_hash=referral.candidate_pan_hash
        )
        assert status.is_in_cooling is True
        assert status.days_remaining is not None
        assert 165 <= status.days_remaining <= 175
        assert status.cooling_end == end.date()
        # Sanity check: today is between start and end.
        assert date.today() <= end.date()
