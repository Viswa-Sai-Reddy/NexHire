"""College lookup + autocomplete (decision A7).

Two read shapes:
  * `search(query, limit)` — type-ahead via pg_trgm similarity on the
    canonical name plus exact alias match. Returns ranked results.
  * `get_by_id(id)` — direct fetch when the form already has the id.

The college list is seeded at install. Unknown colleges submitted
through the referrer form become `is_verified=false` rows that HR can
verify or merge from S25 — that workflow lands in S6.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral.models import College

logger = logging.getLogger("nexhire.colleges")


async def get_by_id(session: AsyncSession, college_id: UUID) -> College | None:
    return (
        await session.execute(select(College).where(College.id == college_id))
    ).scalar_one_or_none()


async def search(
    session: AsyncSession,
    *,
    query: str,
    limit: int = 10,
) -> list[College]:
    """Trigram-similarity search over `canonical_name`, with alias
    match boost. The `pg_trgm` GIN index from migration 0007 keeps
    this O(log n) even at full scale.
    """
    cleaned = query.strip()
    if not cleaned:
        return []

    # Use raw SQL for the similarity ranking — SQLAlchemy's ORM
    # doesn't expose `%` operator cleanly across drivers.
    rows = (
        await session.execute(
            text(
                """
                SELECT id,
                       canonical_name,
                       aliases,
                       location_state,
                       type,
                       is_verified,
                       created_at,
                       updated_at,
                       similarity(canonical_name, :q) AS sim
                FROM colleges
                WHERE canonical_name ILIKE :prefix
                   OR aliases @> jsonb_build_array(:q_upper)
                   OR canonical_name % :q
                ORDER BY sim DESC NULLS LAST, canonical_name ASC
                LIMIT :limit
                """
            ).bindparams(
                q=cleaned,
                prefix=f"%{cleaned}%",
                q_upper=cleaned.upper(),
                limit=limit,
            )
        )
    ).mappings().all()

    return [
        College(
            id=row["id"],
            canonical_name=row["canonical_name"],
            aliases=row["aliases"] or [],
            location_state=row["location_state"],
            type=row["type"],
            is_verified=row["is_verified"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def get_active_referral_count(
    session: AsyncSession,
    *,
    referrer_id: UUID,
    college_id: UUID,
) -> int:
    """Drives RULE-E2 (max 2 active referrals per referrer per college).

    Reads the `referrer_college_counts` view created in migration 0009,
    which already filters out terminal statuses.
    """
    result = await session.execute(
        text(
            """
            SELECT COALESCE(active_count, 0) AS n
            FROM referrer_college_counts
            WHERE referrer_id = :ref
              AND college_id = :col
            """
        ).bindparams(ref=referrer_id, col=college_id)
    )
    row = result.scalar_one_or_none()
    return int(row or 0)
