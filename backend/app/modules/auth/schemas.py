"""Auth Pydantic schemas — HTTP request/response shapes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.shared.constants import UserRole


class LoginRequest(BaseModel):
    """Body of POST /auth/login. Email + password authentication."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


# Roles that humans can self-register as. Excludes SYSTEM (AI actor) and
# CANDIDATE (created automatically when a referral is approved).
RegistrableRole = Literal[
    "REFERRER",
    "MENTOR",
    "HR",
    "IT_AD",
    "ADMIN",
    "PROGRAM_OWNER",
]


class RegisterRequest(BaseModel):
    """Body of POST /auth/register. Self-serve account creation."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: RegistrableRole


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    user_id: UUID
    # Plain str (not EmailStr) so reserved-domain seeds like
    # `program-owner@example.com` don't fail response validation.
    email: str
    full_name: str
    role: UserRole
    can_mentor: bool
    out_of_office_until: datetime | None = None


class JwksResponse(BaseModel):
    """OIDC-compatible JWKS payload at /.well-known/jwks.json."""

    keys: list[dict[str, str]]
