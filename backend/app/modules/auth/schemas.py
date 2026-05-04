"""Auth Pydantic schemas — HTTP request/response shapes."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.shared.constants import UserRole


class AzureAdLoginRequest(BaseModel):
    """Body of POST /auth/login. Frontend MSAL has just acquired an ID
    token from Azure AD; we exchange it for a NexHire JWT.
    """

    azure_id_token: str = Field(..., min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUserResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    can_mentor: bool
    out_of_office_until: datetime | None = None


class JwksResponse(BaseModel):
    """OIDC-compatible JWKS payload at /.well-known/jwks.json."""

    keys: list[dict[str, str]]
