"""Duplicate-detector normalization helpers.

Pure functions that decide *what counts as the same person*. If these
drift, dedup quality drifts.
"""
from __future__ import annotations

import pytest

from app.modules.ai.duplicate_detector import (
    _normalize_email,
    _normalize_name,
    _normalize_phone,
)


class TestEmailNormalization:
    @pytest.mark.parametrize(
        ("a", "b"),
        [
            ("alice@example.com", "ALICE@example.com"),
            ("alice@example.com", "alice+tag@example.com"),
            ("  Alice@Example.com  ", "alice@example.com"),
        ],
    )
    def test_treated_as_equal(self, a: str, b: str) -> None:
        assert _normalize_email(a) == _normalize_email(b)

    def test_different_locals(self) -> None:
        assert _normalize_email("alice@example.com") != _normalize_email(
            "bob@example.com"
        )


class TestPhoneNormalization:
    def test_strip_country_code_and_punctuation(self) -> None:
        assert _normalize_phone("+91 98765 43210") == "9876543210"
        assert _normalize_phone("(987) 654-3210") == "9876543210"
        assert _normalize_phone("9876543210") == "9876543210"

    def test_missing_phone_is_none(self) -> None:
        assert _normalize_phone(None) is None
        assert _normalize_phone("") is None


class TestNameNormalization:
    def test_collapses_whitespace_and_case(self) -> None:
        assert (
            _normalize_name("  RIYA   Sharma ")
            == _normalize_name("riya sharma")
            == "riya sharma"
        )

    def test_unicode_compatibility(self) -> None:
        # NFKC normalizes ligatures + accent forms — different inputs
        # that visually look identical should be treated equal.
        assert _normalize_name("Sıva Kumar") == _normalize_name("Sıva Kumar")
