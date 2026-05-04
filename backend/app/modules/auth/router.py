"""FastAPI router for /auth/* and /.well-known/jwks.json."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.auth import jwt_service, service
from app.modules.auth.schemas import (
    AzureAdLoginRequest,
    CurrentUserResponse,
    JwksResponse,
    RefreshRequest,
    TokenResponse,
)


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
    summary="Exchange an Azure AD ID token for a NexHire JWT.",
)
async def login(
    body: AzureAdLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    return await service.login_with_azure_id_token(
        session=session,
        id_token=body.azure_id_token,
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
        email=principal.email,  # type: ignore[arg-type]  # EmailStr subset of str
        full_name="",  # populated by the auth router only when DB read is desired
        role=principal.role,
        can_mentor=principal.can_mentor,
    )
