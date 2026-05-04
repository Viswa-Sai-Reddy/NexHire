"""S6 admin config service — mentor threshold + cooling-period edits."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin import config_service
from app.modules.referral.models import (
    ConfigChangeHistory,
    CoolingPeriodConfig,
    MentorThresholdConfig,
)
from app.shared.constants import ReferralStatus, UserRole
from app.shared.exceptions import (
    CannotPenalizeCandidateRejectedError,
    ConfigValueUnchangedError,
    InsufficientPermissionsError,
    InvalidCoolingDurationError,
    InvalidMentorThresholdError,
)
from tests.factories import make_user


pytestmark = pytest.mark.asyncio


class TestMentorThreshold:
    async def test_update_writes_history_and_audit(
        self, session: AsyncSession
    ) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        await config_service.set_mentor_threshold(
            session,
            new_value=5,
            actor_user_id=po.id,
            actor_role=UserRole.PROGRAM_OWNER,
            reason="Program expansion Q3 2026",
        )
        current = (
            await session.execute(
                select(MentorThresholdConfig).where(
                    MentorThresholdConfig.is_current.is_(True)
                )
            )
        ).scalar_one()
        assert current.max_mentees == 5

        history = (
            await session.execute(
                select(ConfigChangeHistory).where(
                    ConfigChangeHistory.config_type == "MENTOR_THRESHOLD"
                )
            )
        ).scalars().all()
        assert any(h.new_value == "5" for h in history)

    async def test_non_po_blocked(self, session: AsyncSession) -> None:
        hr = await make_user(session, role="HR")
        with pytest.raises(InsufficientPermissionsError):
            await config_service.set_mentor_threshold(
                session,
                new_value=6,
                actor_user_id=hr.id,
                actor_role=UserRole.HR,
            )

    async def test_invalid_range(self, session: AsyncSession) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        with pytest.raises(InvalidMentorThresholdError):
            await config_service.set_mentor_threshold(
                session,
                new_value=11,
                actor_user_id=po.id,
                actor_role=UserRole.PROGRAM_OWNER,
            )

    async def test_unchanged_value_rejected(
        self, session: AsyncSession
    ) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        with pytest.raises(ConfigValueUnchangedError):
            await config_service.set_mentor_threshold(
                session,
                new_value=4,  # already the seed default
                actor_user_id=po.id,
                actor_role=UserRole.PROGRAM_OWNER,
            )


class TestCoolingPeriod:
    async def test_update_succeeds(self, session: AsyncSession) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        await config_service.set_cooling_period(
            session,
            terminal_state=ReferralStatus.HR_REJECTED.value,
            new_duration_months=6,
            actor_user_id=po.id,
            actor_role=UserRole.PROGRAM_OWNER,
            reason="Industry benchmark alignment",
        )
        row = (
            await session.execute(
                select(CoolingPeriodConfig).where(
                    CoolingPeriodConfig.terminal_state == ReferralStatus.HR_REJECTED.value
                )
            )
        ).scalar_one()
        assert row.duration_months == 6

    async def test_candidate_rejected_locked_at_zero(
        self, session: AsyncSession
    ) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        with pytest.raises(CannotPenalizeCandidateRejectedError):
            await config_service.set_cooling_period(
                session,
                terminal_state=ReferralStatus.CANDIDATE_REJECTED.value,
                new_duration_months=3,
                actor_user_id=po.id,
                actor_role=UserRole.PROGRAM_OWNER,
            )

    async def test_out_of_range_rejected(self, session: AsyncSession) -> None:
        po = await make_user(session, role="PROGRAM_OWNER")
        with pytest.raises(InvalidCoolingDurationError):
            await config_service.set_cooling_period(
                session,
                terminal_state=ReferralStatus.HR_REJECTED.value,
                new_duration_months=30,
                actor_user_id=po.id,
                actor_role=UserRole.PROGRAM_OWNER,
            )
