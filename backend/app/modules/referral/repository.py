"""Read/write helpers for the Referral aggregate.

The repository is intentionally thin — it owns SQL but no business
logic. The orchestrator (service.py) composes these calls with the
validator + AI service + mentor service + audit publisher inside one
transaction.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.onboarding.models import Intern
from app.modules.referral.models import Referral

logger = logging.getLogger("nexhire.referral.repo")


async def get(session: AsyncSession, referral_id: UUID) -> Referral | None:
    return (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()


async def list_for_referrer(
    session: AsyncSession,
    *,
    referrer_id: UUID,
    limit: int = 50,
) -> Sequence[tuple[Referral, Intern | None]]:
    """Return (referral, intern?) pairs for a referrer.

    The intern row is None until HR approves the referral. Callers that
    only need referral fields can ignore the second tuple element.
    """
    rows = await session.execute(
        select(Referral, Intern)
        .outerjoin(Intern, Intern.referral_id == Referral.id)
        .where(Referral.referrer_id == referrer_id)
        .order_by(Referral.created_at.desc())
        .limit(limit)
    )
    return [(r, i) for r, i in rows.all()]


async def list_for_mentor(
    session: AsyncSession,
    *,
    mentor_id: UUID,
    limit: int = 50,
) -> Sequence[Referral]:
    rows = await session.execute(
        select(Referral)
        .where(Referral.mentor_id == mentor_id)
        .order_by(Referral.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())
