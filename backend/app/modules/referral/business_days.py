"""Business-day calculator — decision A12.

Holidays come from the `holidays` table (seeded at install + editable
by Program Owner via S25). Weekend = Sat/Sun.

We expose two operations:
  * `add_business_days(start, n)` — when does `start + n business days`
    fall? Used by SLA scheduling.
  * `count_business_days(start, end)` — how many business days are
    between two timestamps? Used by reporting.

Both round to *days*: a SLA of "1 business day" expressed as hours is
a no-go because a 5pm submission on Monday vs 9am Tuesday produces
different results without making business sense. SLA hours within a
day are computed against clock-time elsewhere (decision B15).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral.models import Holiday


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5 = Sat, 6 = Sun


async def _holidays_in_range(
    session: AsyncSession, *, start: date, end: date
) -> set[date]:
    rows = await session.execute(
        select(Holiday.date).where(Holiday.date >= start, Holiday.date <= end)
    )
    return {cast("date", row[0]) for row in rows}


async def add_business_days(
    session: AsyncSession,
    *,
    start: date,
    business_days: int,
) -> date:
    """Return the date that is `business_days` business days after `start`.

    `start` itself is NOT counted; a `business_days=1` request asks "the
    *next* business day". A non-positive count returns `start`.
    """
    if business_days <= 0:
        return start

    # Holidays for a generous window — `business_days * 2` calendar days
    # is more than enough for any plausible SLA.
    horizon_end = start + timedelta(days=business_days * 2 + 7)
    holidays = await _holidays_in_range(session, start=start, end=horizon_end)

    cursor = start
    remaining = business_days
    while remaining > 0:
        cursor += timedelta(days=1)
        if not _is_weekend(cursor) and cursor not in holidays:
            remaining -= 1
    return cursor


async def count_business_days(
    session: AsyncSession, *, start: date, end: date
) -> int:
    """Inclusive on both ends. `count(start, start)` for a weekday = 1."""
    if end < start:
        return 0
    holidays = await _holidays_in_range(session, start=start, end=end)
    total = 0
    cursor = start
    while cursor <= end:
        if not _is_weekend(cursor) and cursor not in holidays:
            total += 1
        cursor += timedelta(days=1)
    return total


@lru_cache(maxsize=64)
def _cached_weekend(d: date) -> bool:
    return _is_weekend(d)


def is_business_day(d: datetime | date, *, holidays: set[date]) -> bool:
    """Synchronous variant — caller supplies the holiday set. Used by
    in-memory tests where we don't want to hit the DB.
    """
    plain = d.date() if isinstance(d, datetime) else d
    return not _cached_weekend(plain) and plain not in holidays
