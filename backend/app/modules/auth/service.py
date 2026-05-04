"""Auth service — exchanges an Azure AD ID token for a NexHire JWT.

S0 path:
  1. Validate the incoming Azure AD ID token (azure_ad.validate_id_token).
  2. `oid` claim → look up `users.azure_oid`. If missing, create the
     user with `role=NULL`-ish state until an admin assigns a real role.
     For the bootstrap user (the seeded Program Owner) the role is set
     by the seed migration so they can log in immediately.
  3. Issue NexHire access + refresh tokens.
  4. Persist the refresh-token hash to `sessions`.
  5. Audit `LOGIN`. Publish `UserLoggedIn` event for any subscriber.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.auth import azure_ad, jwt_service
from app.modules.auth.models import Session as SessionRow, User
from app.modules.auth.schemas import TokenResponse
from app.shared.constants import UserRole
from app.shared.domain_events import UserCreated, UserLoggedIn
from app.shared.exceptions import (
    InsufficientPermissionsError,
    SsoTokenInvalidError,
)
from app.shared.value_objects import UserId

logger = logging.getLogger("nexhire.auth")


def _hash_refresh(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_refresh(token: str, hashed: str) -> bool:
    return bcrypt.checkpw(token.encode("utf-8"), hashed.encode("utf-8"))


async def login_with_azure_id_token(
    *,
    session: AsyncSession,
    id_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    claims = await azure_ad.validate_id_token(id_token)
    azure_oid = str(claims.get("oid") or claims.get("sub") or "")
    email_raw = str(claims.get("preferred_username") or claims.get("email") or "").lower()
    name = str(claims.get("name") or email_raw or "Unknown")
    if not azure_oid or not email_raw:
        raise SsoTokenInvalidError(user_message="ID token is missing required claims.")

    user, created = await _get_or_create_user(
        session, azure_oid=azure_oid, email=email_raw, name=name
    )

    if not user.is_active:
        raise InsufficientPermissionsError(user_message="This account is deactivated.")
    if not user.role:
        # Bootstrapped users always have a role; this catches inconsistent state.
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
        event_type="USER_CREATED" if created else "LOGIN",
        entity_type="USER",
        entity_id=user.id,
        actor_user_id=user.id,
        actor_role=user.role,
        ip_address=ip_address,
        user_agent=user_agent,
        payload={"email": user.email, "azure_oid": azure_oid},
        session=session,
    )

    # Domain events fire after the audit (audit is the source of truth).
    from app.infrastructure.event_bus import get_bus

    bus = get_bus()
    if created:
        await bus.publish(
            UserCreated(
                user_id=UserId(user.id),
                email=user.email,
                role=user.role,
                azure_oid=azure_oid,
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


async def _get_or_create_user(
    session: AsyncSession,
    *,
    azure_oid: str,
    email: str,
    name: str,
) -> tuple[User, bool]:
    """Find by azure_oid; if missing, find by email; if still missing,
    create the row.

    The "find by email" fallback handles the case where the seeded PO
    row was created before the user logged in for the first time and
    hence has `azure_oid IS NULL`. On first login we backfill the OID.
    """
    user = (
        await session.execute(select(User).where(User.azure_oid == azure_oid))
    ).scalar_one_or_none()
    if user:
        return user, False

    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user:
        # Backfill OID + name; preserve role.
        user.azure_oid = azure_oid
        user.full_name = name
        user.updated_at = datetime.now(timezone.utc)
        return user, False

    # Truly new — minimal record. The role MUST be set by an admin
    # before the user can use the app. Login responses for these users
    # surface INSUFFICIENT_PERMISSIONS until that happens (see caller).
    user = User(
        azure_oid=azure_oid,
        email=email,
        full_name=name,
        role="",  # placeholder — caller will reject login until set
        can_mentor=False,
        is_active=True,
    )
    session.add(user)
    await session.flush()  # assign user.id without committing the outer txn
    return user, True


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
                SessionRow.expires_at > datetime.now(timezone.utc),
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

    matched.revoked_at = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
    for row in rows:
        if raw_refresh_token is None or _verify_refresh(
            raw_refresh_token, row.refresh_token_hash
        ):
            row.revoked_at = now


def claims_payload(claims: dict[str, Any]) -> dict[str, Any]:
    """Minimal helper for tests — turns Azure AD claims into the user
    fields we'd expect to persist. Not part of the public API.
    """
    return {
        "azure_oid": claims.get("oid") or claims.get("sub"),
        "email": (claims.get("preferred_username") or claims.get("email") or "").lower(),
        "name": claims.get("name"),
    }


# Re-exports for convenience.
__all__ = [
    "claims_payload",
    "login_with_azure_id_token",
    "logout",
    "refresh_session",
    "UserRole",
]
