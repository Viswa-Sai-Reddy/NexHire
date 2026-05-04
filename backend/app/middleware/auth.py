"""JWT validation + RBAC enforcement.

Layers:
  * `get_current_user` — FastAPI dependency that validates the JWT and
    returns a `Principal` (user_id, role, ...). Raises `JwtExpiredError`
    or `JwtInvalidError` on bad tokens.
  * `require(*permissions)` — annotation-driven permission check.
    Returns a dependency that the route declares; the actual permission
    matrix lives in `modules/auth/rbac.py`.

We keep RBAC *out* of the middleware. The matrix is policy + lives in
the auth module. Middleware here only wires the JWT verification and
exposes the principal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from jose import JWTError, jwt

from app.config import get_settings
from app.middleware.logging import actor_user_id_ctx
from app.shared.constants import UserRole
from app.shared.exceptions import (
    JwtExpiredError,
    JwtInvalidError,
)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated actor for the current request."""

    user_id: UUID
    email: str
    role: UserRole
    can_mentor: bool = False
    intern_id: UUID | None = None  # populated only for CANDIDATE tokens


def _decode(token: str) -> dict[str, object]:
    cfg = get_settings()
    if not cfg.jwt_public_key_pem:
        # In development without keys configured we fail fast rather
        # than silently accepting tokens.
        raise JwtInvalidError(user_message="JWT key material is not configured.")
    try:
        return jwt.decode(
            token,
            cfg.jwt_public_key_pem,
            algorithms=["RS256"],
            audience=cfg.jwt_audience,
            issuer=cfg.jwt_issuer,
        )
    except jwt.ExpiredSignatureError as exc:
        raise JwtExpiredError() from exc
    except JWTError as exc:
        raise JwtInvalidError() from exc


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve and validate the bearer token. Returns the principal.

    Raises if the token is missing / expired / invalid. The error
    handler maps to the appropriate HTTP status.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise JwtInvalidError(user_message="Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    claims = _decode(token)

    try:
        principal = Principal(
            user_id=UUID(str(claims["sub"])),
            email=str(claims.get("email", "")),
            role=UserRole(str(claims["role"])),
            can_mentor=bool(claims.get("can_mentor", False)),
            intern_id=(UUID(str(claims["intern_id"])) if claims.get("intern_id") else None),
        )
    except (KeyError, ValueError) as exc:
        raise JwtInvalidError(user_message="Token claims are malformed.") from exc

    actor_user_id_ctx.set(str(principal.user_id))
    return principal


CurrentUser = Annotated[Principal, Depends(get_current_user)]
