"""NDA lifecycle — issue, sign, decline, auto-reject."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nda import service as nda_service
from app.modules.nda.models import NdaRecord
from app.modules.onboarding import magic_link
from app.modules.referral import pan_crypto
from app.modules.referral.models import Referral
from app.shared.constants import (
    NdaStatus,
    ReferralStatus,
)
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _intern_at_id_issued(session: AsyncSession):  # type: ignore[no-untyped-def]
    referrer = await make_user(session, role="REFERRER")
    college = await make_college(session)
    start, end = future_dates()
    pan = random_pan()
    referral = Referral(
        referrer_id=referrer.id,
        candidate_name="NDA Test",
        candidate_email=f"nda-{pan.lower()}@example.com",
        candidate_phone="+919999000000",
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
        status=ReferralStatus.ID_ISSUED.value,
        current_stage=ReferralStatus.ID_ISSUED.value,
    )
    session.add(referral)
    await session.flush()
    _, intern, _ = await magic_link.provision_candidate(
        session,
        referral_id=referral.id,
        candidate_email=referral.candidate_email,
        candidate_name=referral.candidate_name,
    )
    intern.non_worker_id = "NW-TESTPAN-2026"
    await session.flush()
    return intern, referral


class TestNdaIssue:
    async def test_issue_creates_record_and_advances_status(
        self, session: AsyncSession
    ) -> None:
        intern, referral = await _intern_at_id_issued(session)
        record = await nda_service.issue_for_intern(session, intern_id=intern.id)
        assert record.status == NdaStatus.SENT.value
        assert record.opensign_envelope_id  # dev or real
        await session.refresh(referral)
        assert referral.status == ReferralStatus.NDA_PENDING.value


class TestSign:
    async def test_signed_path(self, session: AsyncSession) -> None:
        intern, referral = await _intern_at_id_issued(session)
        record = await nda_service.issue_for_intern(session, intern_id=intern.id)
        await nda_service.mark_signed(
            session,
            envelope_id=record.opensign_envelope_id or "",
            signed_at=datetime.now(UTC),
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.NDA_SIGNED.value


class TestDecline:
    async def test_decline_sets_terminal_with_cooling(
        self, session: AsyncSession
    ) -> None:
        intern, referral = await _intern_at_id_issued(session)
        record = await nda_service.issue_for_intern(session, intern_id=intern.id)
        await nda_service.mark_declined(
            session,
            envelope_id=record.opensign_envelope_id or "",
            declined_at=datetime.now(UTC),
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.NDA_DECLINED_REJECTED.value
        # 6-month cooling per RULE-CP1.
        assert referral.cooling_period_months == 6


class TestAutoReject:
    async def test_day_5_timeout(self, session: AsyncSession) -> None:
        intern, referral = await _intern_at_id_issued(session)
        record = await nda_service.issue_for_intern(session, intern_id=intern.id)
        # Backdate `sent_at` past the deadline.
        record.sent_at = datetime.now(UTC) - timedelta(days=6)
        await session.flush()

        handled = await nda_service.auto_reject_expired(session)
        assert handled >= 1
        await session.refresh(referral)
        assert referral.status == ReferralStatus.NDA_TIMEOUT_REJECTED.value
        assert referral.cooling_period_months == 3
        # NDA record updated.
        record_after = (
            await session.execute(
                select(NdaRecord).where(NdaRecord.id == record.id)
            )
        ).scalar_one()
        assert record_after.status == NdaStatus.EXPIRED.value
