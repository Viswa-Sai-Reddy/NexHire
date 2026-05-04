"""AI-2 mentor matcher — pure scoring functions.

Each dimension is independently testable; we don't need a DB to verify
that Jaccard is computed correctly or that response-speed bucketing
matches the spec.
"""
from __future__ import annotations

import pytest

from app.modules.ai.mentor_matcher import (
    _score_availability,
    _score_familiarity,
    _score_reputation,
    _score_response_speed,
    _score_skill,
)


class TestSkillScore:
    def test_perfect_overlap(self) -> None:
        assert _score_skill(["python", "ml"], ["Python", "ML"]) == 20

    def test_partial_overlap(self) -> None:
        # Jaccard = 1/3 → 7 (round)
        score = _score_skill(["python", "java"], ["python", "go"])
        assert score == round((1 / 3) * 20)

    def test_disjoint(self) -> None:
        assert _score_skill(["python"], ["go"]) == 0

    def test_empty_inputs(self) -> None:
        assert _score_skill([], []) == 0
        assert _score_skill(["python"], []) == 0


class TestAvailability:
    def test_full_capacity_zero(self) -> None:
        assert _score_availability(active_mentees=4, threshold=4) == 0

    def test_empty_capacity_full(self) -> None:
        assert _score_availability(active_mentees=0, threshold=4) == 20

    def test_half_capacity(self) -> None:
        assert _score_availability(active_mentees=2, threshold=4) == 10

    def test_zero_threshold_safe(self) -> None:
        assert _score_availability(active_mentees=0, threshold=0) == 0


class TestReputation:
    def test_no_history_neutral(self) -> None:
        assert _score_reputation(None) == 12

    @pytest.mark.parametrize(
        ("rate", "expected"),
        [(0.0, 0), (0.5, 10), (0.8, 16), (1.0, 20)],
    )
    def test_proportional(self, rate: float, expected: int) -> None:
        assert _score_reputation(rate) == expected


class TestResponseSpeed:
    @pytest.mark.parametrize(
        ("hours", "expected"),
        [(None, 12), (1.0, 20), (3.0, 15), (8.0, 10), (18.0, 5), (48.0, 0)],
    )
    def test_buckets(self, hours: float | None, expected: int) -> None:
        assert _score_response_speed(hours) == expected


class TestFamiliarity:
    def test_same_state_full(self) -> None:
        assert (
            _score_familiarity(
                mentor_states=["Karnataka"], candidate_state="Karnataka"
            )
            == 20
        )

    def test_no_candidate_state(self) -> None:
        assert (
            _score_familiarity(mentor_states=["Karnataka"], candidate_state=None) == 5
        )

    def test_different_states(self) -> None:
        assert (
            _score_familiarity(
                mentor_states=["Karnataka"], candidate_state="Tamil Nadu"
            )
            == 5
        )
