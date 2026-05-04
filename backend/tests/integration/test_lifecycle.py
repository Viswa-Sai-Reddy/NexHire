"""S5 lifecycle: confirm-start → extension → completion → terminate."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.lifecycle import service as lifecycle
from app.modules.onboarding import magic_link
from app.modules.referral import pan_crypto
from app.modules.referral.models import Referral
from app.shared.constants import (
    AdAccountStatus,
    InternStatus,
    ReferralStatus,
    UserRole,
)
from app.shared.exceptions import (
    ExtensionLimitReachedError,
    InvalidExtensionDurationError,
)
from tests.factories import future_dates, make_college, make_user, random_pan


pytestmark = pytest.mark.asyncio


async def _intern_at_access_pending(session: AsyncSession):  # type: ignore[no-untyped-def]
    referrer = await make_user(session, role="REFERRER")
    mentor = await make_user(session, role="MENTOR", can_mentor=True)
    college = await make_college(session)
    start, end = future_dates(weeks=8)
    pan = random_pan()
    referral = Referral(
        referrer_id=referrer.id,
        mentor_id=mentor.id,
        candidate_name="Lifecycle Test",
        candidate_email=f"lc-{pan.lower()}@example.com",
        candidate_phone="+919876123456",
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
        status=ReferralStatus.ACCESS_PENDING.value,
        current_stage=ReferralStatus.ACCESS_PENDING.value,
    )
    session.add(referral)
    await session.flush()
    _, intern, _ = await magic_link.provision_candidate(
        session,
        referral_id=referral.id,
        candidate_email=referral.candidate_email,
        candidate_name=referral.candidate_name,
    )
    intern.ad_account_status = AdAccountStatus.PROVISIONED.value
    intern.ad_account_username = "intern.upn@nexhire.local"
    referral.status = ReferralStatus.ACCESS_PENDING.value
    await session.flush()
    return intern, referral, mentor


class TestConfirmStart:
    async def test_advances_to_active(
        self, session: AsyncSession
    ) -> None:
        intern, referral, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )
        await session.refresh(intern)
        await session.refresh(referral)
        assert intern.status == InternStatus.ACTIVE.value
        assert referral.status == ReferralStatus.ACTIVE.value


class TestExtension:
    async def test_extension_within_caps(
        self, session: AsyncSession
    ) -> None:
        intern, referral, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )
        await session.refresh(intern)
        new_end = (referral.internship_end_date or date.today()) + timedelta(days=14)
        await lifecycle.request_extension(
            session,
            intern_id=intern.id,
            actor_user_id=mentor.id,
            actor_role=UserRole.MENTOR,
            new_end_date=new_end,
            reason="Project scope expanded for paper deadline.",
        )
        await session.refresh(intern)
        assert intern.extension_count == 1
        assert intern.actual_end_date == new_end

    async def test_third_extension_blocked(
        self, session: AsyncSession
    ) -> None:
        intern, referral, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )
        for _ in range(2):
            await session.refresh(intern)
            current_end = intern.actual_end_date or referral.internship_end_date
            new_end = (current_end or date.today()) + timedelta(days=14)
            await lifecycle.request_extension(
                session,
                intern_id=intern.id,
                actor_user_id=mentor.id,
                actor_role=UserRole.MENTOR,
                new_end_date=new_end,
                reason="Need more weeks for the rollout.",
            )
        await session.refresh(intern)
        third_end = (intern.actual_end_date or date.today()) + timedelta(days=14)
        with pytest.raises(ExtensionLimitReachedError):
            await lifecycle.request_extension(
                session,
                intern_id=intern.id,
                actor_user_id=mentor.id,
                actor_role=UserRole.MENTOR,
                new_end_date=third_end,
                reason="Would be the third extension.",
            )

    async def test_oversized_extension_blocked(
        self, session: AsyncSession
    ) -> None:
        intern, referral, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )
        await session.refresh(intern)
        too_far = (referral.internship_end_date or date.today()) + timedelta(days=60)
        with pytest.raises(InvalidExtensionDurationError):
            await lifecycle.request_extension(
                session,
                intern_id=intern.id,
                actor_user_id=mentor.id,
                actor_role=UserRole.MENTOR,
                new_end_date=too_far,
                reason="60-day extension is over the cap.",
            )


class TestClosure:
    async def test_confirm_completion_moves_to_closure_pending(
        self, session: AsyncSession
    ) -> None:
        intern, _, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )
        await lifecycle.confirm_completion(
            session,
            intern_id=intern.id,
            mentor_user_id=mentor.id,
            feedback={
                "project_summary": "Improved inference throughput by 18% on the staging pipeline.",
                "skills_demonstrated": ["python", "ml"],
                "recommendation_strength": 4,
                "notable_contributions": "Took ownership of the fallback path tests.",
            },
        )
        await session.refresh(intern)
        assert intern.status == InternStatus.CLOSURE_PENDING.value


class TestTermination:
    @pytest.mark.parametrize(
        ("role",),
        [(UserRole.MENTOR,), (UserRole.HR,), (UserRole.CANDIDATE,)],
    )
    async def test_three_actors_can_terminate(
        self, session: AsyncSession, role: UserRole
    ) -> None:
        intern, referral, mentor = await _intern_at_access_pending(session)
        await lifecycle.confirm_start(
            session, intern_id=intern.id, mentor_user_id=mentor.id
        )

        if role is UserRole.HR:
            actor = await make_user(session, role="HR")
            actor_id = actor.id
        elif role is UserRole.CANDIDATE:
            actor_id = intern.user_id
        else:
            actor_id = mentor.id

        await lifecycle.terminate(
            session,
            intern_id=intern.id,
            actor_user_id=actor_id,
            actor_role=role,
            reason="Family emergency required immediate departure.",
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.TERMINATED.value
        assert referral.cooling_period_months == 6  # RULE-CP2
