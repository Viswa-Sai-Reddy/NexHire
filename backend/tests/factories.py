"""Tiny test factories.

Avoiding `factory_boy` for the moment — the indirection isn't worth it
when we have ~5 tables to seed and the values are set per-test.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.referral.models import College


async def make_user(
    session: AsyncSession,
    *,
    email: str | None = None,
    role: str = "REFERRER",
    can_mentor: bool = False,
    full_name: str | None = None,
) -> User:
    suffix = uuid4().hex[:6]
    user = User(
        email=email or f"user-{suffix}@example.com",
        full_name=full_name or f"User {suffix}",
        role=role,
        can_mentor=can_mentor,
    )
    session.add(user)
    await session.flush()
    return user


async def make_college(
    session: AsyncSession,
    *,
    name: str | None = None,
) -> College:
    suffix = uuid4().hex[:6]
    college = College(
        canonical_name=name or f"Test College {suffix}",
        aliases=[],
        location_state="Karnataka",
        type="GOVT_AUTONOMOUS",
        is_verified=True,
    )
    session.add(college)
    await session.flush()
    return college


def future_dates(*, weeks: int = 8) -> tuple[date, date]:
    today = date.today()
    start = today + timedelta(days=14)
    end = start + timedelta(weeks=weeks)
    return start, end


def random_pan() -> str:
    """Generate a syntactically-valid random PAN for tests."""
    import secrets
    import string

    rng = secrets.SystemRandom()
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(5))
    digits = "".join(rng.choice(string.digits) for _ in range(4))
    last = rng.choice(string.ascii_uppercase)
    return f"{letters}{digits}{last}"


__all__ = ["future_dates", "make_college", "make_user", "random_pan"]


# Suppress unused-import warning when the file is loaded standalone.
_ = UUID
