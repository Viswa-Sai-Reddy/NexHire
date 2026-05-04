"""Mentor request → accept / reject / 3-strike terminal."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mentor import service as mentor_service
from app.modules.referral import pan_crypto
from app.modules.referral.models import MentorAssignment, Referral
from app.shared.constants import (
    MentorAssignmentStatus,
    ReferralStatus,
)
from tests.factories import future_dates, make_college, make_user, random_pan


pytestmark = pytest.mark.asyncio


async def _seed_for_assignment(session: AsyncSession) -> tuple[Referral, str]:
    """Build a SUBMITTED referral pinned to a mentor."""
    referrer = await make_user(session)
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates()
    pan = random_pan()
    referral = Referral(
        referrer_id=referrer.id,
        mentor_id=mentor.id,
        candidate_name="Mentor Test",
        candidate_email=f"m-{pan.lower()}@example.com",
        candidate_phone="+919999000111",
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
        project_title="Test",
        status=ReferralStatus.SUBMITTED.value,
        current_stage=ReferralStatus.SUBMITTED.value,
    )
    session.add(referral)
    await session.flush()
    return referral, str(mentor.id)


async def _assign_and_get_tokens(
    session: AsyncSession, referral: Referral
) -> tuple[str, str]:
    assignment, accept, reject = await mentor_service.request_assignment(
        session,
        referral_id=referral.id,
        mentor_id=referral.mentor_id,  # type: ignore[arg-type]
        referrer_id=referral.referrer_id,
    )
    assert assignment.status == MentorAssignmentStatus.PENDING.value
    return accept.raw_token, reject.raw_token


class TestAcceptFlow:
    async def test_accept_transitions_to_accepted(
        self, session: AsyncSession
    ) -> None:
        referral, _mentor = await _seed_for_assignment(session)
        accept_token, _reject_token = await _assign_and_get_tokens(
            session, referral
        )

        await mentor_service.accept(session, raw_token=accept_token)
        await session.refresh(referral)
        assert referral.status == ReferralStatus.MENTOR_ACCEPTED.value
        assert referral.mentor_attempt_count == 1

        # Reject token (sibling) is now invalidated; can't be replayed.
        from app.shared.exceptions import ActionTokenUsedError

        with pytest.raises(ActionTokenUsedError):
            await mentor_service.reject(
                session,
                raw_token=_reject_token,
                reason="Trying to reject after accept already happened",
            )


class TestRejectFlow:
    async def test_first_reject_returns_to_pending(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seed_for_assignment(session)
        _, reject_token = await _assign_and_get_tokens(session, referral)

        _, is_terminal = await mentor_service.reject(
            session,
            raw_token=reject_token,
            reason="Capacity issues this quarter",
        )
        assert is_terminal is False
        await session.refresh(referral)
        assert referral.status == ReferralStatus.MENTOR_PENDING.value
        assert referral.mentor_attempt_count == 1

    async def test_three_rejects_lead_to_terminal(
        self, session: AsyncSession
    ) -> None:
        referral, _ = await _seed_for_assignment(session)
        for attempt in range(1, 4):
            _, reject_token = await _assign_and_get_tokens(session, referral)
            _, is_terminal = await mentor_service.reject(
                session,
                raw_token=reject_token,
                reason=f"Attempt {attempt} reason — busy this quarter",
            )
            await session.refresh(referral)
            if attempt < 3:
                assert is_terminal is False
                assert referral.status == ReferralStatus.MENTOR_PENDING.value
            else:
                assert is_terminal is True
                assert referral.status == ReferralStatus.CANDIDATE_REJECTED.value
                assert referral.rejection_reason == "MAX_MENTOR_ATTEMPTS_EXCEEDED"


class TestTimeoutHandler:
    async def test_pending_past_timeout_advances_attempt(
        self, session: AsyncSession
    ) -> None:
        from datetime import datetime, timedelta, timezone

        referral, _ = await _seed_for_assignment(session)
        await _assign_and_get_tokens(session, referral)

        # Roll the assignment's timeout into the past.
        assignment = (
            await session.execute(
                select(MentorAssignment).where(
                    MentorAssignment.referral_id == referral.id
                )
            )
        ).scalar_one()
        assignment.timeout_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.flush()

        handled = await mentor_service.handle_timeouts(session)
        assert handled >= 1

        await session.refresh(referral)
        await session.refresh(assignment)
        assert assignment.status == MentorAssignmentStatus.TIMED_OUT.value
        assert referral.mentor_attempt_count == 1
        # Attempt 1 timed out → still room for two more attempts.
        assert referral.status == ReferralStatus.MENTOR_PENDING.value
