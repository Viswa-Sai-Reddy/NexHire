"""FastAPI router for /auth/* and /.well-known/jwks.json."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware import audit
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.auth import jwt_service, service
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    CurrentUserResponse,
    JwksResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.shared.exceptions import BusinessRuleError

# `/auth/*` is mounted under the API prefix; JWKS is unprefixed (RFC 8414).
auth_router = APIRouter(prefix="/auth", tags=["auth"])
jwks_router = APIRouter(tags=["auth"])


@jwks_router.get(
    "/.well-known/jwks.json",
    response_model=JwksResponse,
    summary="Public keys for verifying NexHire JWTs.",
)
async def get_jwks() -> JSONResponse:
    return JSONResponse(jwt_service.jwks())


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Exchange email + password for a NexHire JWT.",
)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    return await service.login_with_email_password(
        session=session,
        email=body.email,
        password=body.password,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("User-Agent"),
    )


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Self-serve account creation. Returns tokens (auto-login).",
)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    return await service.register_user(
        session=session,
        payload=body,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("User-Agent"),
    )


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("default"))],
    summary="Rotate a refresh token for a new access + refresh pair.",
)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    return await service.refresh_session(
        session=session, raw_refresh_token=body.refresh_token
    )


@auth_router.post(
    "/logout",
    status_code=204,
    summary="Revoke the current refresh token (or all if not supplied).",
)
async def logout(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
    body: RefreshRequest | None = None,
) -> None:
    await service.logout(
        session=session,
        user_id=principal.user_id,
        raw_refresh_token=body.refresh_token if body else None,
    )


@auth_router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Return the currently authenticated principal.",
)
async def me(principal: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse(
        user_id=principal.user_id,
        email=principal.email,
        full_name="",  # populated by the auth router only when DB read is desired
        role=principal.role,
        can_mentor=principal.can_mentor,
    )


class OutOfOfficeResponse(BaseModel):
    until: datetime | None


class OutOfOfficeRequest(BaseModel):
    until: datetime | None


class SkillsResponse(BaseModel):
    skills: list[str]


class SkillsRequest(BaseModel):
    skills: list[str]


@auth_router.get(
    "/me/out-of-office",
    response_model=OutOfOfficeResponse,
    summary="Get the caller's out-of-office expiry (E6 — feeds AI-10 routing).",
)
async def get_out_of_office(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> OutOfOfficeResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessRuleError(user_message="User record not found.")
    return OutOfOfficeResponse(until=user.out_of_office_until)


@auth_router.put(
    "/me/out-of-office",
    response_model=OutOfOfficeResponse,
    dependencies=[Depends(rate_limit("default"))],
    summary="Set or clear the caller's out-of-office expiry.",
)
async def set_out_of_office(
    body: OutOfOfficeRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> OutOfOfficeResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessRuleError(user_message="User record not found.")

    now = datetime.now(UTC)
    if body.until is not None and body.until <= now:
        raise BusinessRuleError(
            user_message="Out-of-office expiry must be in the future."
        )

    previous = user.out_of_office_until
    user.out_of_office_until = body.until
    user.updated_at = now

    await audit.publish(
        event_type="OUT_OF_OFFICE_UPDATED",
        entity_type="USER",
        entity_id=user.id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        payload={
            "previous_until": previous.isoformat() if previous else None,
            "new_until": body.until.isoformat() if body.until else None,
        },
        session=session,
    )
    return OutOfOfficeResponse(until=user.out_of_office_until)


@auth_router.get(
    "/me/skills",
    response_model=SkillsResponse,
    summary="Get the caller's skill set (feeds AI-2 mentor matching).",
)
async def get_my_skills(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> SkillsResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessRuleError(user_message="User record not found.")
    return SkillsResponse(skills=list(user.skills or []))


@auth_router.put(
    "/me/skills",
    response_model=SkillsResponse,
    dependencies=[Depends(rate_limit("default"))],
    summary="Replace the caller's skill set. Normalized to lowercase, deduped.",
)
async def set_my_skills(
    body: SkillsRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> SkillsResponse:
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessRuleError(user_message="User record not found.")

    cleaned = _clean_skills(body.skills)
    if len(cleaned) > 50:
        raise BusinessRuleError(
            user_message="Skill list cannot exceed 50 entries.",
            details={"count": len(cleaned)},
        )

    previous = list(user.skills or [])
    user.skills = cleaned
    user.updated_at = datetime.now(UTC)

    await audit.publish(
        event_type="USER_SKILLS_UPDATED",
        entity_type="USER",
        entity_id=user.id,
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        payload={
            "previous_count": len(previous),
            "new_count": len(cleaned),
        },
        session=session,
    )
    return SkillsResponse(skills=list(user.skills or []))


def _clean_skills(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in raw:
        norm = (s or "").strip().lower()
        if not norm or len(norm) > 64 or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out
