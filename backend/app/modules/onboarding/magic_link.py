"""Magic-link service for candidate portal access (F-03).

Three operations:
  * `provision_candidate(...)` — create the candidate `users` row + the
    `interns` row + an empty `joining_forms` shell + the first
    CANDIDATE_ACCESS token. Called by the ReferralApproved handler.
  * `issue_fresh_link(...)` — re-mint a magic link (HR resend, candidate
    self-resend). Invalidates older active CANDIDATE_ACCESS tokens for
    the same intern.
  * `redeem(...)` — validates a token, returns a candidate JWT scoped
    to `intern_id`, and returns the redirect target keyed off
    `intern.status` per F-03 step 5.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.auth import jwt_service
from app.modules.auth.models import ActionToken, User
from app.modules.mentor import action_tokens
from app.modules.onboarding.models import Intern, JoiningForm
from app.modules.referral.models import Referral
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    MAGIC_LINK_EXPIRY_HOURS,
    ActionTokenType,
    InternStatus,
    ReferralStatus,
    UserRole,
)
from app.shared.domain_events import CandidateMagicLinkIssued
from app.shared.value_objects import InternId, ReferralId, UserId

logger = logging.getLogger("nexhire.onboarding.magic_link")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ────────────────────────────────────────────────────────────────────
# Candidate provisioning — fires on `ReferralApproved`.
# ────────────────────────────────────────────────────────────────────
async def provision_candidate(
    session: AsyncSession,
    *,
    referral_id: UUID,
    candidate_email: str,
    candidate_name: str,
) -> tuple[User, Intern, action_tokens.IssuedToken]:
    """Idempotent: if the candidate user already exists, reuse it."""
    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one()

    user = (
        await session.execute(
            select(User).where(User.email == candidate_email.lower())
        )
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=candidate_email.lower(),
            full_name=candidate_name,
            role=UserRole.CANDIDATE.value,
            can_mentor=False,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    elif user.role != UserRole.CANDIDATE.value:
        # Refusing to silently coerce the role would erase the existing
        # account's referrer/mentor/HR access. HR must resolve manually.
        from app.shared.exceptions import BusinessRuleError

        raise BusinessRuleError(
            user_message=(
                "This email is already registered with a different role. "
                "Use a different candidate email or ask an administrator "
                "to merge or archive the existing account."
            ),
            details={
                "code_hint": "CANDIDATE_EMAIL_COLLISION",
                "existing_role": user.role,
                "candidate_email": candidate_email.lower(),
            },
        )

    intern = (
        await session.execute(
            select(Intern).where(Intern.referral_id == referral.id)
        )
    ).scalar_one_or_none()
    if intern is None:
        intern = Intern(
            referral_id=referral.id,
            user_id=user.id,
            status=InternStatus.PENDING.value,
        )
        session.add(intern)
        await session.flush()

        session.add(JoiningForm(intern_id=intern.id))
        await session.flush()

    # Invalidate any older candidate-access tokens, then mint a fresh one.
    await _invalidate_candidate_tokens(session, intern_id=intern.id)
    issued = await action_tokens.issue(
        session,
        action_type=ActionTokenType.CANDIDATE_ACCESS,
        actor_user_id=user.id,
        intern_id=intern.id,
        expiry_days=max(1, MAGIC_LINK_EXPIRY_HOURS // 24),
    )

    # Bump the referral status into the joining-form-pending lane.
    if referral.status == ReferralStatus.APPROVED.value:
        referral.status = ReferralStatus.JOINING_FORM_PENDING.value
        referral.current_stage = ReferralStatus.JOINING_FORM_PENDING.value
        referral.stage_entered_at = _utcnow()
        referral.updated_at = _utcnow()

    await audit.publish(
        event_type="MAGIC_LINK_ISSUED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "candidate_user_id": str(user.id),
            "referral_id": str(referral.id),
            "expires_at": issued.expires_at.isoformat(),
        },
        session=session,
    )

    logger.info(
        f"provision_candidate: publishing CandidateMagicLinkIssued "
        f"referral_id={referral.id} intern_id={intern.id} "
        f"candidate_email={user.email}"
    )
    await get_bus().publish(
        CandidateMagicLinkIssued(
            referral_id=ReferralId(referral.id),
            intern_id=InternId(intern.id),
            candidate_email=user.email,
            candidate_name=user.full_name,
            raw_token=issued.raw_token,
            expires_at=issued.expires_at,
        )
    )

    return user, intern, issued


async def issue_fresh_link(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: UUID | None = None,
) -> action_tokens.IssuedToken:
    """HR-driven resend or candidate self-resend.

    Older unused CANDIDATE_ACCESS tokens are *not* invalidated here.
    Each token is single-use (consumed on redeem) and time-bounded by
    `MAGIC_LINK_EXPIRY_HOURS`, so multiple concurrent magic links can
    safely coexist. This avoids the failure mode where a candidate
    requests a fresh link and the older email's link suddenly stops
    working — they can use whichever link they have at hand.
    """
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    user = (
        await session.execute(select(User).where(User.id == intern.user_id))
    ).scalar_one()

    issued = await action_tokens.issue(
        session,
        action_type=ActionTokenType.CANDIDATE_ACCESS,
        actor_user_id=intern.user_id,
        intern_id=intern.id,
        expiry_days=max(1, MAGIC_LINK_EXPIRY_HOURS // 24),
    )
    await audit.publish(
        event_type="MAGIC_LINK_REISSUED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=actor_user_id or AI_SYSTEM_USER_ID,
        actor_role="HR" if actor_user_id else "SYSTEM",
        payload={"expires_at": issued.expires_at.isoformat()},
        session=session,
    )

    await get_bus().publish(
        CandidateMagicLinkIssued(
            referral_id=ReferralId(intern.referral_id),
            intern_id=InternId(intern.id),
            candidate_email=user.email,
            candidate_name=user.full_name,
            raw_token=issued.raw_token,
            expires_at=issued.expires_at,
        )
    )
    return issued


# ────────────────────────────────────────────────────────────────────
# Candidate auth — token → JWT.
# ────────────────────────────────────────────────────────────────────
async def redeem(
    session: AsyncSession,
    *,
    raw_token: str,
    ip_address: str | None = None,
) -> tuple[User, Intern, str, int, str]:
    """Validate the magic link, mark it consumed, return:

        (user, intern, access_token, expires_in_seconds, redirect_path)

    Tokens are single-use. After redemption a fresh JWT lasts 8h; the
    candidate doesn't get a refresh token (decision F-03 — limited-scope
    session).
    """
    token = await action_tokens.validate(
        session,
        raw_token=raw_token,
        expected_action=ActionTokenType.CANDIDATE_ACCESS,
        mark_used=True,
        ip_address=ip_address,
    )
    if token.intern_id is None or token.actor_user_id is None:
        from app.shared.exceptions import MagicLinkInvalidError

        raise MagicLinkInvalidError()

    intern = (
        await session.execute(select(Intern).where(Intern.id == token.intern_id))
    ).scalar_one()
    user = (
        await session.execute(select(User).where(User.id == token.actor_user_id))
    ).scalar_one()

    # Self-heal: legacy candidates whose joining form was locked before
    # the inline-NW-ID fix can land here without an NW-ID. Generate one
    # lazily so they never hit a dead-end "(pending)" state.
    if intern.non_worker_id is None:
        referral_for_heal = (
            await session.execute(
                select(Referral).where(Referral.id == intern.referral_id)
            )
        ).scalar_one()
        past_lock_states = {
            ReferralStatus.JOINING_FORM_LOCKED.value,
            ReferralStatus.ID_PENDING.value,
            ReferralStatus.ID_ISSUED.value,
            ReferralStatus.NDA_PENDING.value,
            ReferralStatus.NDA_SIGNED.value,
            ReferralStatus.ACCESS_PENDING.value,
            ReferralStatus.ACTIVE.value,
            ReferralStatus.EXTENDED.value,
            ReferralStatus.CLOSURE_PENDING.value,
            ReferralStatus.CLOSED.value,
        }
        if referral_for_heal.status in past_lock_states:
            from app.modules.onboarding import non_worker_id as nw_id_service

            try:
                await nw_id_service.generate_for_intern(
                    session, intern_id=intern.id
                )
                logger.info(
                    "nexhire.magic_link.nw_id_self_healed",
                    extra={"intern_id": str(intern.id)},
                )
            except Exception:
                logger.exception(
                    "nexhire.magic_link.nw_id_self_heal_failed",
                    extra={"intern_id": str(intern.id)},
                )

    access_token, expires_in = jwt_service.issue_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        can_mentor=False,
        intern_id=intern.id,
    )

    redirect = await _redirect_for_status(intern, session)
    await audit.publish(
        event_type="MAGIC_LINK_USED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=user.id,
        actor_role="CANDIDATE",
        ip_address=ip_address,
        payload={"redirect": redirect},
        session=session,
    )
    return user, intern, access_token, expires_in, redirect


async def _redirect_for_status(intern: Intern, session: AsyncSession) -> str:
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()
    status = referral.status
    if status in (
        ReferralStatus.APPROVED.value,
        ReferralStatus.JOINING_FORM_PENDING.value,
        ReferralStatus.CORRECTION_NEEDED.value,
    ):
        return "/candidate/joining-form"
    if status in (
        ReferralStatus.JOINING_FORM_LOCKED.value,
        ReferralStatus.ID_PENDING.value,
        ReferralStatus.ID_ISSUED.value,
        ReferralStatus.NDA_PENDING.value,
    ):
        return "/candidate/nda"
    if status in (
        ReferralStatus.NDA_SIGNED.value,
        ReferralStatus.ACCESS_PENDING.value,
        ReferralStatus.ACTIVE.value,
        ReferralStatus.EXTENDED.value,
    ):
        return "/candidate/status"
    if status == ReferralStatus.CLOSURE_PENDING.value:
        return "/candidate/certificate"
    if status == ReferralStatus.CLOSED.value:
        return "/candidate/certificate"
    return "/candidate/status"


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
async def _invalidate_candidate_tokens(
    session: AsyncSession, *, intern_id: UUID
) -> None:
    await session.execute(
        update(ActionToken)
        .where(
            ActionToken.intern_id == intern_id,
            ActionToken.action_type == ActionTokenType.CANDIDATE_ACCESS.value,
            ActionToken.used.is_(False),
        )
        .values(used=True, used_at=_utcnow())
    )


__all__ = ["issue_fresh_link", "provision_candidate", "redeem"]


# Suppress unused-import warning when the file is loaded standalone.
_ = ReferralId, InternId, UserId
