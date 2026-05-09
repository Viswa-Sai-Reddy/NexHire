"""S3 onboarding pipeline — provisioning + auto-lock + Non-Worker ID."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import ActionToken, User
from app.modules.onboarding import auto_lock, magic_link, non_worker_id, service
from app.modules.onboarding.models import JoiningForm
from app.modules.referral import pan_crypto
from app.modules.referral.models import Referral
from app.shared.constants import (
    ActionTokenType,
    JoiningFormStatus,
    ReferralStatus,
    UserRole,
)
from tests.factories import future_dates, make_college, make_user, random_pan

pytestmark = pytest.mark.asyncio


async def _approved_referral(session: AsyncSession) -> Referral:
    referrer = await make_user(session, role="REFERRER")
    college = await make_college(session)
    start, end = future_dates()
    pan = random_pan()
    referral = Referral(
        referrer_id=referrer.id,
        candidate_name="Riya Sharma",
        candidate_email=f"riya-{pan.lower()}@example.com",
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
        status=ReferralStatus.APPROVED.value,
        current_stage=ReferralStatus.APPROVED.value,
    )
    session.add(referral)
    await session.flush()
    return referral


class TestProvisioning:
    async def test_provision_creates_user_intern_token(
        self, session: AsyncSession
    ) -> None:
        referral = await _approved_referral(session)
        user, intern, issued = await magic_link.provision_candidate(
            session,
            referral_id=referral.id,
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
        )
        assert user.role == UserRole.CANDIDATE.value
        assert intern.referral_id == referral.id
        # Token row exists, hash-stored, scoped to intern.
        token = (
            await session.execute(
                select(ActionToken).where(ActionToken.id == issued.token_id)
            )
        ).scalar_one()
        assert token.action_type == ActionTokenType.CANDIDATE_ACCESS.value
        assert token.intern_id == intern.id
        assert token.used is False
        # Joining form shell created.
        form = (
            await session.execute(
                select(JoiningForm).where(JoiningForm.intern_id == intern.id)
            )
        ).scalar_one()
        assert form.status == JoiningFormStatus.DRAFT.value


class TestSubmitAutoLock:
    async def test_clean_form_auto_locks_and_generates_nw_id(
        self, session: AsyncSession
    ) -> None:
        referral = await _approved_referral(session)
        user, intern, _ = await magic_link.provision_candidate(
            session,
            referral_id=referral.id,
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
        )
        # Hydrate a clean form: matching name, signed declaration.
        form = (
            await session.execute(
                select(JoiningForm).where(JoiningForm.intern_id == intern.id)
            )
        ).scalar_one()
        plain_pan = pan_crypto.decrypt_to_pan(referral.candidate_pan_encrypted)
        form.personal_details = {
            "full_name": referral.candidate_name,
            "date_of_birth": "2002-04-01",
        }
        form.address = {"current_address": "123 Lane, Bangalore"}
        form.emergency_contact = {
            "name": "Parent",
            "phone": "+919999999999",
        }
        form.govt_ids = {"pan_number": plain_pan.value}
        form.declaration_signed = True
        await session.flush()

        result = await service.submit(session, intern_id=intern.id)
        assert result.decision == "AUTO_LOCK"

        await session.refresh(form)
        assert form.status == JoiningFormStatus.LOCKED.value
        assert form.locked_by_label == "AI_AUTO_LOCK"

        _ = user

    async def test_name_mismatch_still_auto_locks(
        self, session: AsyncSession
    ) -> None:
        """Flagged forms still auto-lock; flags are persisted on
        `ai_auto_actions` so HR can recall within the existing window
        if needed.
        """
        referral = await _approved_referral(session)
        _, intern, _ = await magic_link.provision_candidate(
            session,
            referral_id=referral.id,
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
        )
        form = (
            await session.execute(
                select(JoiningForm).where(JoiningForm.intern_id == intern.id)
            )
        ).scalar_one()
        plain_pan = pan_crypto.decrypt_to_pan(referral.candidate_pan_encrypted)
        form.personal_details = {
            "full_name": "Completely Different Person",
            "date_of_birth": "2002-04-01",
        }
        form.govt_ids = {"pan_number": plain_pan.value}
        form.emergency_contact = {"name": "P", "phone": "+919999"}
        form.declaration_signed = True
        await session.flush()

        result = await service.submit(session, intern_id=intern.id)

        assert result.decision == "AUTO_LOCK"
        assert any(
            "differs from the referral" in f.message
            for f in result.high_flags
        )

        await session.refresh(form)
        assert form.status == JoiningFormStatus.LOCKED.value
        assert form.locked_by_label == "AI_AUTO_LOCK"

        from app.modules.referral.models import AiAutoAction

        action = (
            await session.execute(
                select(AiAutoAction).where(AiAutoAction.intern_id == intern.id)
            )
        ).scalar_one()
        assert action.decision == "EXECUTED"
        assert action.flags is not None
        assert any("differs from the referral" in f for f in action.flags)


class TestNonWorkerId:
    async def test_auto_generated_format(
        self, session: AsyncSession
    ) -> None:
        referral = await _approved_referral(session)
        _, intern, _ = await magic_link.provision_candidate(
            session,
            referral_id=referral.id,
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
        )
        nw_id = await non_worker_id.generate_for_intern(
            session, intern_id=intern.id
        )
        plain_pan = pan_crypto.decrypt_to_pan(referral.candidate_pan_encrypted)
        assert nw_id.startswith(f"NW-{plain_pan.value}-")

    async def test_collision_appends_sequence(
        self, session: AsyncSession
    ) -> None:
        referral_1 = await _approved_referral(session)
        _, intern_1, _ = await magic_link.provision_candidate(
            session,
            referral_id=referral_1.id,
            candidate_email=referral_1.candidate_email,
            candidate_name=referral_1.candidate_name,
        )
        await non_worker_id.generate_for_intern(session, intern_id=intern_1.id)
        # Second intern with the same PAN somehow (e.g. cooling override
        # → re-referral): collision should produce `…-2`.
        referral_2 = await _approved_referral(session)
        # Force same PAN.
        referral_2.candidate_pan_hash = referral_1.candidate_pan_hash
        referral_2.candidate_pan_encrypted = referral_1.candidate_pan_encrypted
        referral_2.candidate_pan_masked = referral_1.candidate_pan_masked
        referral_2.internship_start_date = referral_1.internship_start_date
        await session.flush()
        _, intern_2, _ = await magic_link.provision_candidate(
            session,
            referral_id=referral_2.id,
            candidate_email=referral_2.candidate_email,
            candidate_name=referral_2.candidate_name,
        )
        nw_2 = await non_worker_id.generate_for_intern(
            session, intern_id=intern_2.id
        )
        assert nw_2.endswith("-2")


# Suppress unused-import warning when the file is loaded standalone.
_ = User, auto_lock
