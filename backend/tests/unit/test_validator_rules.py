"""Synchronous validator rules — RULE-E1..E5 + dates + referrer/mentor."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.modules.referral import validator
from app.shared.exceptions import (
    GraduatedStudentIneligibleError,
    InpersonReadyRequiredError,
    InvalidDateRangeError,
    InvalidStartDatePastError,
    InvalidYearOfStudyError,
    ReferrerIsMentorError,
    UnpaidConsentRequiredError,
)


class TestYearOfStudy:
    def test_2nd_year_passes(self) -> None:
        validator.validate_year_of_study(2, graduation_year=2027, current_year=2026)

    @pytest.mark.parametrize("year", [3, 4])
    def test_3rd_4th_pass(self, year: int) -> None:
        validator.validate_year_of_study(year, graduation_year=2027, current_year=2026)

    def test_1st_year_blocked(self) -> None:
        with pytest.raises(InvalidYearOfStudyError):
            validator.validate_year_of_study(1, graduation_year=2028, current_year=2026)

    def test_already_graduated_blocked(self) -> None:
        with pytest.raises(GraduatedStudentIneligibleError):
            validator.validate_year_of_study(4, graduation_year=2025, current_year=2026)

    def test_graduating_this_year_blocked(self) -> None:
        # `graduation_year ≤ current_year` is the rule — equality counts.
        with pytest.raises(GraduatedStudentIneligibleError):
            validator.validate_year_of_study(4, graduation_year=2026, current_year=2026)


class TestReferrerNotMentor:
    def test_distinct_ids_pass(self) -> None:
        validator.validate_referrer_mentor(
            referrer_id=uuid4(), mentor_id=uuid4()
        )

    def test_no_mentor_yet_passes(self) -> None:
        validator.validate_referrer_mentor(referrer_id=uuid4(), mentor_id=None)

    def test_same_id_blocked(self) -> None:
        same = uuid4()
        with pytest.raises(ReferrerIsMentorError):
            validator.validate_referrer_mentor(referrer_id=same, mentor_id=same)


class TestConsents:
    def test_unpaid_required(self) -> None:
        with pytest.raises(UnpaidConsentRequiredError):
            validator.require_unpaid_consent(False)

    def test_inperson_required(self) -> None:
        with pytest.raises(InpersonReadyRequiredError):
            validator.require_inperson_ready(False)


class TestDates:
    def setup_method(self) -> None:
        self.today = date(2026, 6, 1)

    def test_happy_path(self) -> None:
        validator.validate_dates(
            start=self.today + timedelta(days=10),
            end=self.today + timedelta(days=10 + 56),  # 8 weeks
            today=self.today,
        )

    def test_past_start_blocked(self) -> None:
        with pytest.raises(InvalidStartDatePastError):
            validator.validate_dates(
                start=self.today - timedelta(days=1),
                end=self.today + timedelta(days=60),
                today=self.today,
            )

    def test_end_before_start_blocked(self) -> None:
        with pytest.raises(InvalidDateRangeError):
            validator.validate_dates(
                start=self.today + timedelta(days=20),
                end=self.today + timedelta(days=10),
                today=self.today,
            )

    @pytest.mark.parametrize("days", [27, 183])
    def test_duration_outside_range_blocked(self, days: int) -> None:
        with pytest.raises(InvalidDateRangeError):
            validator.validate_dates(
                start=self.today + timedelta(days=2),
                end=self.today + timedelta(days=2 + days),
                today=self.today,
            )

    @pytest.mark.parametrize("days", [28, 56, 91, 182])
    def test_durations_in_range_pass(self, days: int) -> None:
        validator.validate_dates(
            start=self.today + timedelta(days=2),
            end=self.today + timedelta(days=2 + days),
            today=self.today,
        )
