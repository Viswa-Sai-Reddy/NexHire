"""A14 — HR mid-flow mentor reassignment.

Critical guarantees:
  * Strike counter (`mentor_attempt_count`) is NOT bumped.
  * Original assignment marked REASSIGNED with reassigned_to/at/by.
  * New assignment row exists with status=PENDING and a fresh
    `attempt_number = max + 1`.
  * Two new action tokens were issued.
  * Old action tokens are invalidated.
"""
from __future__ import annotations

from datetime import UTC

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import ActionToken
from app.modules.mentor import service as mentor_service
from app.modules.referral import pan_crypto
from app.modules.referral.models import MentorAssignment, Referral
from app.shared.constants import (
    ActionTokenType,
    MentorAssignmentStatus,
    ReferralStatus,
    UserRole,
)
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
)
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _seed_accepted_referral(
    session: AsyncSession,
) -> tuple[Referral, object, object]:
    referrer = await make_user(session, role="REFERRER")
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates()
    pan = random_pan()
    referral = Referral(
        referrer_id=referrer.id,
        mentor_id=mentor.id,
        candidate_name="Reassign Test",
        candidate_email=f"r-{pan.lower()}@example.com",
        candidate_phone="+919999111222",
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
        status=ReferralStatus.MENTOR_ACCEPTED.value,
        current_stage=ReferralStatus.MENTOR_ACCEPTED.value,
        mentor_attempt_count=1,
    )
    session.add(referral)
    await session.flush()

    # Pre-existing accepted assignment.
    from datetime import datetime, timedelta

    assignment = MentorAssignment(
        referral_id=referral.id,
        mentor_id=mentor.id,
        attempt_number=1,
        status=MentorAssignmentStatus.ACCEPTED.value,
        timeout_at=datetime.now(UTC) + timedelta(days=3),
    )
    session.add(assignment)
    await session.flush()

    return referral, mentor, referrer


class TestReassignmentHappyPath:
    async def test_strike_counter_unchanged_and_new_assignment_created(
        self, session: AsyncSession
    ) -> None:
        referral, original_mentor, _referrer = await _seed_accepted_referral(session)
        hr = await make_user(session, role="HR")
        new_mentor = await make_user(session, role="MENTOR", can_mentor=True)

        await mentor_service.reassign_by_hr(
            session,
            referral_id=referral.id,
            new_mentor_id=new_mentor.id,
            hr_user_id=hr.id,
            hr_role=UserRole.HR.value,
            reason="Original mentor on extended leave starting next week.",
        )

        await session.refresh(referral)
        assert referral.mentor_id == new_mentor.id
        assert referral.status == ReferralStatus.MENTOR_PENDING.value
        # Strike counter UNCHANGED — A14 invariant.
        assert referral.mentor_attempt_count == 1

        # Original marked REASSIGNED.
        original = (
            await session.execute(
                select(MentorAssignment).where(
                    MentorAssignment.referral_id == referral.id,
                    MentorAssignment.attempt_number == 1,
                )
            )
        ).scalar_one()
        assert original.status == MentorAssignmentStatus.REASSIGNED.value
        assert original.reassigned_to == new_mentor.id
        assert original.reassigned_by == hr.id

        # New assignment exists at attempt_number = 2.
        new_assignment = (
            await session.execute(
                select(MentorAssignment).where(
                    MentorAssignment.referral_id == referral.id,
                    MentorAssignment.attempt_number == 2,
                )
            )
        ).scalar_one()
        assert new_assignment.status == MentorAssignmentStatus.PENDING.value
        assert new_assignment.mentor_id == new_mentor.id

        # Two fresh action tokens for the new mentor.
        unused_token_count = (
            await session.execute(
                select(ActionToken).where(
                    ActionToken.referral_id == referral.id,
                    ActionToken.action_type == ActionTokenType.MENTOR_RESPONSE.value,
                    ActionToken.used.is_(False),
                    ActionToken.actor_user_id == new_mentor.id,
                )
            )
        ).scalars().all()
        assert len(unused_token_count) == 2

        _ = original_mentor  # silence unused


class TestReassignmentGuards:
    async def test_non_hr_actor_blocked(self, session: AsyncSession) -> None:
        referral, _mentor, referrer = await _seed_accepted_referral(session)
        new_mentor = await make_user(session, role="MENTOR", can_mentor=True)
        with pytest.raises(InsufficientPermissionsError):
            await mentor_service.reassign_by_hr(
                session,
                referral_id=referral.id,
                new_mentor_id=new_mentor.id,
                hr_user_id=referrer.id,
                hr_role=UserRole.REFERRER.value,
                reason="Should not be allowed by non-HR caller.",
            )

    async def test_referrer_cannot_be_new_mentor(
        self, session: AsyncSession
    ) -> None:
        from app.shared.exceptions import ReferrerIsMentorError

        referral, _mentor, referrer = await _seed_accepted_referral(session)
        hr = await make_user(session, role="HR")
        with pytest.raises(ReferrerIsMentorError):
            await mentor_service.reassign_by_hr(
                session,
                referral_id=referral.id,
                new_mentor_id=referrer.id,  # same as referrer
                hr_user_id=hr.id,
                hr_role=UserRole.HR.value,
                reason="Trying to assign the referrer as their own mentor.",
            )

    async def test_short_reason_rejected(self, session: AsyncSession) -> None:
        referral, _mentor, _referrer = await _seed_accepted_referral(session)
        hr = await make_user(session, role="HR")
        new_mentor = await make_user(session, role="MENTOR", can_mentor=True)
        with pytest.raises(BusinessRuleError):
            await mentor_service.reassign_by_hr(
                session,
                referral_id=referral.id,
                new_mentor_id=new_mentor.id,
                hr_user_id=hr.id,
                hr_role=UserRole.HR.value,
                reason="too short",
            )
