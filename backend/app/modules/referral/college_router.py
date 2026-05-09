"""College autocomplete API.

GET /colleges/search?q=… — top 10 trigram-similar matches.
GET /colleges/{id}     — fetch one (used by review screen).

Open to anyone with `SUBMIT_REFERRAL` (referrers + HR + PO). The list
itself is non-sensitive.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.rate_limit import rate_limit
from app.modules.auth.rbac import Permission, require
from app.modules.referral import college_repository
from app.modules.referral.schemas import CollegeSearchResult
from app.shared.exceptions import BusinessRuleError

college_router = APIRouter(prefix="/colleges", tags=["colleges"])


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
    session: AsyncSession = Depends(get_session),
) -> list[CollegeSearchResult]:
    rows = await college_repository.search(session, query=q, limit=limit)
    return [
        CollegeSearchResult(
            id=row.id,
            canonical_name=row.canonical_name,
            aliases=row.aliases,
            location_state=row.location_state,
            type=row.type,
        )
        for row in rows
    ]


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
