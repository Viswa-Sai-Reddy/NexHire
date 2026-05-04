"""Value objects — shared kernel.

Validated primitives for cross-module use. They are deliberately minimal:
no DB, no service calls, no business logic. Anything richer belongs in a
module's domain layer.

Rationale for value objects (vs raw `str`):
  - Validation runs at the boundary, never at every read.
  - Type system catches "passed a phone where an email was expected".
  - Equality semantics are well-defined (e.g. emails are case-insensitive).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NewType, Self
from uuid import UUID

# ────────────────────────────────────────────────────────────
# ID aliases. NewType so MyPy distinguishes them but they remain UUIDs
# at runtime — no boxing, no allocation.
# ────────────────────────────────────────────────────────────
UserId = NewType("UserId", UUID)
ReferralId = NewType("ReferralId", UUID)
InternId = NewType("InternId", UUID)
MentorAssignmentId = NewType("MentorAssignmentId", UUID)
DocumentId = NewType("DocumentId", UUID)
ActionTokenId = NewType("ActionTokenId", UUID)
JoiningFormId = NewType("JoiningFormId", UUID)
NdaRecordId = NewType("NdaRecordId", UUID)


# ────────────────────────────────────────────────────────────
# Email — validated, case-normalized.
# RFC 5321/5322 in full is too lenient to be useful; this is the
# "permissive practical" pattern (matches §17.5 InvalidEmailError).
# ────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if not _EMAIL_RE.match(self.value):
            raise ValueError(f"Invalid email: {self.value!r}")
        # Normalize via object.__setattr__ since the dataclass is frozen.
        object.__setattr__(self, "value", self.value.strip().lower())

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw)


# ────────────────────────────────────────────────────────────
# Phone — E.164 ("+91XXXXXXXXXX"), with normalization.
# ────────────────────────────────────────────────────────────
_PHONE_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_PHONE_DIGITS_RE = re.compile(r"\D")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        if not _PHONE_E164_RE.match(cleaned):
            raise ValueError(
                f"Invalid phone (expected E.164, e.g. +919876543210): {self.value!r}"
            )
        object.__setattr__(self, "value", cleaned)

    def normalized_digits(self) -> str:
        """Digits-only form for fuzzy matching across format variants."""
        return _PHONE_DIGITS_RE.sub("", self.value)

    def __str__(self) -> str:
        return self.value

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw)


# ────────────────────────────────────────────────────────────
# PAN — Indian Permanent Account Number (decision A3).
# Format: AAAAA9999A (5 letters, 4 digits, 1 letter). Always uppercase.
# Stored encrypted + hashed; this VO holds the plaintext briefly during
# request handling and is masked for any display.
# ────────────────────────────────────────────────────────────
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


@dataclass(frozen=True, slots=True)
class Pan:
    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip().upper()
        if not _PAN_RE.match(cleaned):
            raise ValueError(
                f"Invalid PAN format (expected ABCDE1234F): {self.value!r}"
            )
        object.__setattr__(self, "value", cleaned)

    def masked(self) -> str:
        """Display form: first 5 + ``****`` + last 1. Spec §18.2.1."""
        return f"{self.value[:5]}****{self.value[-1]}"

    def __str__(self) -> str:
        # Default str() is masked so PAN can never accidentally be logged.
        return self.masked()

    def __repr__(self) -> str:
        return f"Pan({self.masked()!r})"

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(raw)
