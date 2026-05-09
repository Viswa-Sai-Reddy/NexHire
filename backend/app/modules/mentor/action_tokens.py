"""Email action tokens (Blueprint §16.2 + decision B12).

The mentor accept/reject flow uses single-use, time-limited tokens
delivered in the assignment email.

Security model:
  * Generation: 32 random bytes, urlsafe-base64. Raw token only ever
    leaves the process inside the email body.
  * Storage: SHA-256 hash of the raw token. A DB dump can't reuse the
    tokens.
  * Use: hash the incoming token; look up; check `used`, `expires_at`;
    set `used = true` atomically; perform the action.
  * Retry: previously-used token returns `ACTION_TOKEN_USED` so a
    misclick / email pre-fetcher can't replay an action.

Decision B12: GET on the action URL renders a confirmation page
(read-only), POST executes. We expose this split via the router; this
module owns generation + validation only.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import ActionToken
from app.shared.constants import (
    ACTION_TOKEN_EXPIRY_DAYS,
    ActionTokenType,
)
from app.shared.exceptions import (
    ActionTokenExpiredError,
    ActionTokenUsedError,
    MagicLinkInvalidError,
)

logger = logging.getLogger("nexhire.action_tokens")


def _hash_raw(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """Returned to the caller. The `raw_token` is what goes in the
    email link; the row in DB holds only the hash.
    """

    raw_token: str
    token_id: UUID
    expires_at: datetime


async def issue(
    session: AsyncSession,
    *,
    action_type: ActionTokenType,
    actor_user_id: UUID | None = None,
    referral_id: UUID | None = None,
    intern_id: UUID | None = None,
    expiry_days: int = ACTION_TOKEN_EXPIRY_DAYS,
) -> IssuedToken:
    """Generate a fresh token, persist its hash, return raw + id."""
    raw = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(days=expiry_days)

    row = ActionToken(
        token_hash=_hash_raw(raw),
        action_type=action_type.value,
        actor_user_id=actor_user_id,
        referral_id=referral_id,
        intern_id=intern_id,
        expires_at=expires_at,
        used=False,
    )
    session.add(row)
    await session.flush()  # populate row.id without committing the outer txn
    return IssuedToken(raw_token=raw, token_id=row.id, expires_at=expires_at)


async def validate(
    session: AsyncSession,
    *,
    raw_token: str,
    expected_action: ActionTokenType,
    mark_used: bool = False,
    ip_address: str | None = None,
) -> ActionToken:
    """Look up + verify a token. Optionally mark it used.

    Two-step UX (B12):
      * GET /action/mentor?token=… → `mark_used=False`. The browser
        gets a confirmation page; the token is still valid.
      * POST /action/mentor/confirm → `mark_used=True`. The action
        executes and the token is consumed.

    Raises:
        MagicLinkInvalidError: not found / wrong type.
        ActionTokenExpiredError: past `expires_at`.
        ActionTokenUsedError: already consumed.
    """
    incoming_hash = _hash_raw(raw_token)
    row = (
        await session.execute(
            select(ActionToken).where(ActionToken.token_hash == incoming_hash)
        )
    ).scalar_one_or_none()
    if row is None:
        raise MagicLinkInvalidError()
    if row.action_type != expected_action.value:
        # Tokens are type-scoped: a candidate-access token can't be used
        # to accept a mentor assignment, even if the row exists.
        raise MagicLinkInvalidError()
    if row.expires_at <= _utcnow():
        raise ActionTokenExpiredError()
    if row.used:
        raise ActionTokenUsedError()

    if mark_used:
        row.used = True
        row.used_at = _utcnow()
        if ip_address:
            row.ip_address = ip_address

    return row


async def invalidate_siblings(
    session: AsyncSession,
    *,
    referral_id: UUID,
    action_type: ActionTokenType,
) -> int:
    """Mark all unused tokens of `action_type` for this referral as used.

    Called after a mentor responds (accept OR reject) so the *other*
    button in the same email becomes inert. Also called on attempt
    rollover (e.g. mentor times out → tokens for the new attempt
    invalidate the old ones).
    """
    rows = (
        await session.execute(
            select(ActionToken).where(
                ActionToken.referral_id == referral_id,
                ActionToken.action_type == action_type.value,
                ActionToken.used.is_(False),
            )
        )
    ).scalars().all()
    now = _utcnow()
    for row in rows:
        row.used = True
        row.used_at = now
    return len(rows)


__all__ = ["IssuedToken", "invalidate_siblings", "issue", "validate"]
