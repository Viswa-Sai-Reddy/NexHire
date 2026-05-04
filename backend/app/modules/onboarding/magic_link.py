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
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.auth import jwt_service
from app.modules.auth.models import ActionToken, User
from app.modules.mentor import action_tokens
from app.modules.onboarding.models import Intern, JoiningForm
from app.modules.referral.models import Referral
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    ActionTokenType,
    InternStatus,
    MAGIC_LINK_EXPIRY_HOURS,
    ReferralStatus,
    UserRole,
)
from app.shared.value_objects import InternId, ReferralId, UserId

logger = logging.getLogger("nexhire.onboarding.magic_link")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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

    return user, intern, issued


async def issue_fresh_link(
    session: AsyncSession,
    *,
    intern_id: UUID,
    actor_user_id: Optional[UUID] = None,
) -> action_tokens.IssuedToken:
    """HR-driven resend or candidate self-resend. Invalidates older
    active CANDIDATE_ACCESS rows for this intern.
    """
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()

    await _invalidate_candidate_tokens(session, intern_id=intern.id)
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
    return issued


# ────────────────────────────────────────────────────────────────────
# Candidate auth — token → JWT.
# ────────────────────────────────────────────────────────────────────
async def redeem(
    session: AsyncSession,
    *,
    raw_token: str,
    ip_address: Optional[str] = None,
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

    access_token, expires_in = jwt_service.issue_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        can_mentor=False,
        intern_id=intern.id,
    )

    redirect = _redirect_for_status(intern, session)
    await audit.publish(
        event_type="MAGIC_LINK_USED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=user.id,
        actor_role="CANDIDATE",
        ip_address=ip_address,
        payload={"redirect": await redirect},
        session=session,
    )
    return user, intern, access_token, expires_in, await redirect


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
