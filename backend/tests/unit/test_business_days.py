"""Business-day calculator — pure-logic in-memory variant.

The async DB-backed variant is exercised by integration tests; here
we lean on the synchronous `is_business_day(d, holidays=...)` helper
to pin weekend + holiday treatment without the testcontainers cost.
"""
from __future__ import annotations

from datetime import date

from app.modules.referral.business_days import is_business_day


class TestIsBusinessDay:
    def test_weekday_with_no_holidays(self) -> None:
        # 2026-06-01 is a Monday.
        assert is_business_day(date(2026, 6, 1), holidays=set()) is True

    def test_saturday_blocked(self) -> None:
        # 2026-06-06 is a Saturday.
        assert is_business_day(date(2026, 6, 6), holidays=set()) is False

    def test_sunday_blocked(self) -> None:
        # 2026-06-07 is a Sunday.
        assert is_business_day(date(2026, 6, 7), holidays=set()) is False

    def test_holiday_blocked(self) -> None:
        # Republic Day on a weekday counts as non-business.
        republic_day = date(2026, 1, 26)  # Monday
        assert (
            is_business_day(republic_day, holidays={republic_day}) is False
        )

    def test_holiday_set_only_blocks_listed_dates(self) -> None:
        # A weekday adjacent to a holiday is unaffected.
        holiday = date(2026, 1, 26)
        next_day = date(2026, 1, 27)
        assert is_business_day(next_day, holidays={holiday}) is True
