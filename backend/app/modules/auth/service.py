"""Auth service — email + password login and self-serve registration.

Flow:
  1. `login_with_email_password` — look up user by email, bcrypt-verify
     password, issue NexHire access + refresh tokens.
  2. `register_user` — create a new user row with bcrypt-hashed password
     and immediately issue tokens (auto-login).
  3. `refresh_session` — rotate a refresh token for new access + refresh.
  4. `logout` — revoke a refresh token (or all sessions).

Audit + domain events fire on the same boundaries as before; the only
field that's gone is `azure_oid` since we no longer go through AAD.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.auth import jwt_service
from app.modules.auth.models import Session as SessionRow
from app.modules.auth.models import User
from app.modules.auth.schemas import RegisterRequest, TokenResponse
from app.shared.constants import UserRole
from app.shared.domain_events import UserCreated, UserLoggedIn
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
    SsoTokenInvalidError,
)
from app.shared.value_objects import UserId

logger = logging.getLogger("nexhire.auth")


def _hash_refresh(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_refresh(token: str, hashed: str) -> bool:
    return bcrypt.checkpw(token.encode("utf-8"), hashed.encode("utf-8"))


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def login_with_email_password(
    *,
    session: AsyncSession,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    """Validate email + password, issue NexHire tokens.

    All failure modes return the same generic error to avoid leaking
    whether the email exists or just the password is wrong.
    """
    normalized_email = email.strip().lower()

    user = (
        await session.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()

    if user is None or not user.is_active or not user.role:
        raise SsoTokenInvalidError(user_message="Invalid email or password.")
    if not _verify_password(password, user.password_hash):
        raise SsoTokenInvalidError(user_message="Invalid email or password.")

    return await _issue_tokens(
        session=session,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        is_new=False,
    )


async def register_user(
    *,
    session: AsyncSession,
    payload: RegisterRequest,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    """Self-serve user creation. Returns tokens so the caller is
    immediately logged in.

    For demo / hackathon use. Production hardening would gate the role
    selection and require email verification.
    """
    normalized_email = payload.email.strip().lower()

    existing = (
        await session.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise BusinessRuleError(
            user_message="An account with that email already exists.",
            details={"email": normalized_email},
        )

    role = UserRole(payload.role)  # validated by schema; convert to enum string
    user = User(
        email=normalized_email,
        full_name=payload.full_name.strip(),
        role=role.value,
        password_hash=_hash_password(payload.password),
        # Mentor role implies mentor-eligibility — saves a separate admin
        # toggle for demo accounts.
        can_mentor=(role is UserRole.MENTOR),
        is_active=True,
    )
    session.add(user)
    await session.flush()  # populate user.id

    return await _issue_tokens(
        session=session,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        is_new=True,
    )


async def _issue_tokens(
    *,
    session: AsyncSession,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
    is_new: bool,
) -> TokenResponse:
    if not user.is_active:
        raise InsufficientPermissionsError(user_message="This account is deactivated.")
    if not user.role:
        raise InsufficientPermissionsError(
            user_message=(
                "Your account has no role assigned. "
                "Please contact HR to be onboarded into the system."
            )
        )

    access_token, expires_in = jwt_service.issue_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        can_mentor=user.can_mentor,
    )
    refresh_token, refresh_exp = jwt_service.issue_refresh_token()

    session.add(
        SessionRow(
            user_id=user.id,
            refresh_token_hash=_hash_refresh(refresh_token),
            expires_at=refresh_exp,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )

    await audit.publish(
        event_type="USER_CREATED" if is_new else "LOGIN",
        entity_type="USER",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"email": user.email},
        session=session,
    )

    from app.infrastructure.event_bus import get_bus

    bus = get_bus()
    if is_new:
        await bus.publish(
            UserCreated(
                user_id=UserId(user.id),
                email=user.email,
                role=user.role,
                azure_oid=None,
            )
        )
    await bus.publish(
        UserLoggedIn(user_id=UserId(user.id), role=user.role, ip_address=ip_address),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def refresh_session(
    *,
    session: AsyncSession,
    raw_refresh_token: str,
) -> TokenResponse:
    """Validate a refresh token, rotate it, return new tokens."""
    sessions = (
        await session.execute(
            select(SessionRow).where(
                SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > datetime.now(UTC),
            )
        )
    ).scalars().all()

    matched: SessionRow | None = None
    for row in sessions:
        if _verify_refresh(raw_refresh_token, row.refresh_token_hash):
            matched = row
            break
    if matched is None:
        raise SsoTokenInvalidError(user_message="Invalid or expired refresh token.")

    user = (
        await session.execute(select(User).where(User.id == matched.user_id))
    ).scalar_one()

    access_token, expires_in = jwt_service.issue_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        can_mentor=user.can_mentor,
    )
    new_refresh, new_exp = jwt_service.issue_refresh_token()

    matched.revoked_at = datetime.now(UTC)
    session.add(
        SessionRow(
            user_id=user.id,
            refresh_token_hash=_hash_refresh(new_refresh),
            expires_at=new_exp,
            ip_address=matched.ip_address,
            user_agent=matched.user_agent,
        )
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


async def logout(
    *,
    session: AsyncSession,
    user_id: UUID,
    raw_refresh_token: str | None = None,
) -> None:
    """Revoke the supplied refresh token. If none provided, revoke all
    active sessions for the user (logout-everywhere).
    """
    rows = (
        await session.execute(
            select(SessionRow).where(
                SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    now = datetime.now(UTC)
    for row in rows:
        if raw_refresh_token is None or _verify_refresh(
            raw_refresh_token, row.refresh_token_hash
        ):
            row.revoked_at = now


__all__ = [
    "UserRole",
    "login_with_email_password",
    "logout",
    "refresh_session",
    "register_user",
]
