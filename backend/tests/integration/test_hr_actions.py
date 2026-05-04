"""HR review actions: approve / reject / request-correction / recall."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral import pan_crypto
from app.modules.referral.models import (
    AiAutoAction,
    Referral,
    Task,
)
from app.modules.workflow import hr_service, recall
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    ReferralStatus,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.shared.exceptions import (
    InsufficientPermissionsError,
)
from tests.factories import future_dates, make_college, make_user, random_pan


pytestmark = pytest.mark.asyncio


async def _seed_in_status(
    session: AsyncSession,
    *,
    status: str,
    approved_by_label: str | None = None,
) -> Referral:
    referrer = await make_user(session, role="REFERRER")
    college = await make_college(session)
    start, end = future_dates()
    pan = random_pan()
    r = Referral(
        referrer_id=referrer.id,
        candidate_name="HR Test",
        candidate_email=f"hr-{pan.lower()}@example.com",
        candidate_phone="+919876543210",
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
        approved_by_label=approved_by_label,
    )
    session.add(r)
    await session.flush()
    return r


class TestApprove:
    async def test_hr_approve_transitions_and_closes_task(
        self, session: AsyncSession
    ) -> None:
        referral = await _seed_in_status(
            session, status=ReferralStatus.HR_REVIEW.value
        )
        hr = await make_user(session, role="HR")
        # Pre-existing review task (the auto-approval engine would have
        # created one; we mimic that here).
        session.add(
            Task(
                task_type=TaskType.HR_REVIEW.value,
                assigned_to=hr.id,
                sla_deadline=datetime.now(timezone.utc) + timedelta(hours=48),
                referral_id=referral.id,
                status=TaskStatus.PENDING.value,
            )
        )
        await session.flush()

        await hr_service.approve(
            session,
            referral_id=referral.id,
            hr_user_id=hr.id,
            hr_role=UserRole.HR,
            notes="Looks good",
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.APPROVED.value
        assert referral.approved_by_label == "HR"

        task = (
            await session.execute(
                select(Task).where(Task.referral_id == referral.id)
            )
        ).scalar_one()
        assert task.status == TaskStatus.COMPLETED.value
        assert task.completed_by == hr.id

    async def test_non_hr_rejected(self, session: AsyncSession) -> None:
        referral = await _seed_in_status(
            session, status=ReferralStatus.HR_REVIEW.value
        )
        with pytest.raises(InsufficientPermissionsError):
            await hr_service.approve(
                session,
                referral_id=referral.id,
                hr_user_id=referral.referrer_id,
                hr_role=UserRole.REFERRER,
            )


class TestReject:
    async def test_reject_applies_cooling(self, session: AsyncSession) -> None:
        referral = await _seed_in_status(
            session, status=ReferralStatus.HR_REVIEW.value
        )
        hr = await make_user(session, role="HR")

        await hr_service.reject(
            session,
            referral_id=referral.id,
            hr_user_id=hr.id,
            hr_role=UserRole.HR,
            reason="Profile mismatch — insufficient prerequisites covered.",
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.HR_REJECTED.value
        # 3-month cooling per RULE-CP4.
        assert referral.cooling_period_months == 3
        assert referral.cooling_period_end_at is not None
        assert referral.cooling_triggered_by == ReferralStatus.HR_REJECTED.value


class TestRequestCorrection:
    async def test_correction_state_transition(
        self, session: AsyncSession
    ) -> None:
        referral = await _seed_in_status(
            session, status=ReferralStatus.HR_REVIEW.value
        )
        hr = await make_user(session, role="HR")
        await hr_service.request_correction(
            session,
            referral_id=referral.id,
            hr_user_id=hr.id,
            hr_role=UserRole.HR,
            notes="Phone number looks malformed; please re-confirm.",
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.CORRECTION_NEEDED.value


class TestRecall:
    async def test_recall_within_window_reverts_to_hr_review(
        self, session: AsyncSession
    ) -> None:
        referral = await _seed_in_status(
            session,
            status=ReferralStatus.APPROVED.value,
            approved_by_label="AI_AUTO_APPROVAL",
        )
        # Simulate the AUTO_APPROVE record that auto-approval wrote.
        session.add(
            AiAutoAction(
                action_type="AUTO_APPROVE",
                decision="EXECUTED",
                referral_id=referral.id,
                conditions_met=["No flags"],
            )
        )
        await session.flush()

        hr = await make_user(session, role="HR")
        await recall.recall_auto_approve(
            session,
            referral_id=referral.id,
            hr_user_id=hr.id,
            hr_role=UserRole.HR,
            reason="Wanted to double-check the duplicate signal.",
        )
        await session.refresh(referral)
        assert referral.status == ReferralStatus.HR_REVIEW.value
        assert referral.approved_by_label is None

        # New HR_REVIEW task was created.
        task = (
            await session.execute(
                select(Task)
                .where(
                    Task.referral_id == referral.id,
                    Task.task_type == TaskType.HR_REVIEW.value,
                )
                .order_by(Task.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        assert task.status == TaskStatus.PENDING.value

    async def test_recall_after_window_blocked(
        self, session: AsyncSession
    ) -> None:
        referral = await _seed_in_status(
            session,
            status=ReferralStatus.APPROVED.value,
            approved_by_label="AI_AUTO_APPROVAL",
        )
        # AUTO_APPROVE row from 3h ago — past the 2h window.
        session.add(
            AiAutoAction(
                action_type="AUTO_APPROVE",
                decision="EXECUTED",
                referral_id=referral.id,
                executed_at=datetime.now(timezone.utc) - timedelta(hours=3),
            )
        )
        await session.flush()

        hr = await make_user(session, role="HR")
        with pytest.raises(recall.RecallWindowExpiredError):
            await recall.recall_auto_approve(
                session,
                referral_id=referral.id,
                hr_user_id=hr.id,
                hr_role=UserRole.HR,
            )

    async def test_recall_only_for_ai_approvals(
        self, session: AsyncSession
    ) -> None:
        referral = await _seed_in_status(
            session,
            status=ReferralStatus.APPROVED.value,
            approved_by_label="HR",  # human-approved, not AI
        )
        session.add(
            AiAutoAction(
                action_type="AUTO_APPROVE",
                decision="EXECUTED",
                referral_id=referral.id,
            )
        )
        await session.flush()

        hr = await make_user(session, role="HR")
        from app.shared.exceptions import InvalidStateTransitionError

        with pytest.raises(InvalidStateTransitionError):
            await recall.recall_auto_approve(
                session,
                referral_id=referral.id,
                hr_user_id=hr.id,
                hr_role=UserRole.HR,
            )


# Suppress unused-import warning when the file is loaded standalone.
_ = AI_SYSTEM_USER_ID
