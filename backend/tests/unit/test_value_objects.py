"""Unit tests for shared/value_objects — no DB, no async."""
from __future__ import annotations

import pytest

from app.shared.value_objects import Email, Pan, PhoneNumber


class TestEmail:
    def test_valid_email_normalized(self) -> None:
        assert Email("  Foo@Example.com ").value == "foo@example.com"

    @pytest.mark.parametrize("bad", ["", "no-at-sign", "@nope.com", "x@", "x@y"])
    def test_invalid_emails_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Email(bad)


class TestPhoneNumber:
    def test_valid_e164(self) -> None:
        p = PhoneNumber("+919876543210")
        assert p.value == "+919876543210"
        assert p.normalized_digits() == "919876543210"

    @pytest.mark.parametrize(
        "bad",
        ["9876543210", "+0123456789", "+1abc4567890", "", "98765 43210"],
    )
    def test_invalid_phones(self, bad: str) -> None:
        with pytest.raises(ValueError):
            PhoneNumber(bad)


class TestPan:
    def test_valid_pan_uppercased(self) -> None:
        p = Pan("abcde1234f")
        assert p.value == "ABCDE1234F"

    def test_masked_form(self) -> None:
        p = Pan("ABCDE1234F")
        assert p.masked() == "ABCDE****F"
        # Default str/repr never leak the raw value.
        assert "1234" not in str(p)
        assert "1234" not in repr(p)

    @pytest.mark.parametrize(
        "bad",
        ["ABCDE12345", "ABCD1234FE", "ABCDE12 4F", "ABCDEFGHIJ", ""],
    )
    def test_invalid_pans(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Pan(bad)
