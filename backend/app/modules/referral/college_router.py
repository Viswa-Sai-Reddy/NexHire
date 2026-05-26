"""College autocomplete API.

GET /colleges/search?q=… — top 10 trigram-similar matches.
GET /colleges/{id}     — fetch one (used by review screen).

Open to anyone with `SUBMIT_REFERRAL` (referrers + HR + PO). The list
itself is non-sensitive.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import redis_client
from app.infrastructure.database import get_session
from app.middleware.rate_limit import rate_limit
from app.modules.auth.rbac import Permission, require
from app.modules.referral import college_repository
from app.modules.referral.schemas import CollegeSearchResult
from app.shared.exceptions import BusinessRuleError

SEARCH_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h

college_router = APIRouter(prefix="/colleges", tags=["colleges"])


async def _get_cached_search(key: str) -> list[CollegeSearchResult] | None:
    try:
        client = await redis_client.get_client()
        raw = await client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        return [CollegeSearchResult(**item) for item in payload]
    except Exception:
        return None


async def _set_cached_search(key: str, results: list[CollegeSearchResult]) -> None:
    payload = json.dumps(
        [
            {
                "id": str(result.id),
                "canonical_name": result.canonical_name,
                "aliases": result.aliases,
                "location_state": result.location_state,
                "type": result.type,
            }
            for result in results
        ]
    )
    try:
        client = await redis_client.get_client()
        await client.set(key, payload, ex=SEARCH_CACHE_TTL_SECONDS)
    except Exception:
        return


@college_router.get(
    "/search",
    response_model=list[CollegeSearchResult],
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SUBMIT_REFERRAL)),
    ],
    summary="Trigram-similarity college autocomplete.",
)
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
    skip_cache: bool = Query(
        False,
        description="Bypass Redis cache and read the college search results directly from the database.",
    ),
    session: AsyncSession = Depends(get_session),
) -> list[CollegeSearchResult]:
    cleaned = q.strip().lower()
    cache_key = redis_client.k("college_search", cleaned, str(limit))
    if not skip_cache:
        cached = await _get_cached_search(cache_key)
        if cached is not None:
            return cached

    rows = await college_repository.search(session, query=q, limit=limit)
    results = [
        CollegeSearchResult(
            id=row.id,
            canonical_name=row.canonical_name,
            aliases=row.aliases,
            location_state=row.location_state,
            type=row.type,
        )
        for row in rows
    ]

    if not skip_cache:
        await _set_cached_search(cache_key, results)
    return results


@college_router.get(
    "/{college_id}",
    response_model=CollegeSearchResult,
    dependencies=[Depends(require(Permission.SUBMIT_REFERRAL))],
)
async def get_college(
    college_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> CollegeSearchResult:
    row = await college_repository.get_by_id(session, college_id)
    if row is None:
        raise BusinessRuleError(
            user_message="College not found.",
            details={"college_id": str(college_id)},
        )
    return CollegeSearchResult(
        id=row.id,
        canonical_name=row.canonical_name,
        aliases=row.aliases,
        location_state=row.location_state,
        type=row.type,
    )
