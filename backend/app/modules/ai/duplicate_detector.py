"""AI-4 — Duplicate detection.

Two-stage:
  1. **PAN check** (delegated to `validator.pan_check`) — deterministic,
     hard-block on any active PAN match (F-33).
  2. **Fuzzy check** — runs only when the PAN check is CLEAR. Compares
     name + email + phone against the last 24 months of referrals.

This module owns step 2 only (step 1 lives in `validator.py` to keep
the validator's interface complete on its own). The referral service
calls *both* sequentially during submission.

Scoring (Blueprint §7 AI-4):
    email exact match      → +0.6
    phone exact match      → +0.4
    name jaro-winkler ≥ 0.85 → +0.2 × similarity
  Total > 0.9 → SOFT_BLOCK (HR must approve).
  Total 0.6–0.9 → WARN (HR sees flag but submission allowed).
  Total < 0.6  → PASS.

No LLM in the loop — fuzzy match is deterministic, fast, auditable.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from rapidfuzz.distance import JaroWinkler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral.models import Referral
from app.shared.constants import RESUME_RETENTION_MONTHS, ReferralStatus

logger = logging.getLogger("nexhire.ai.duplicates")

MODEL_TOUCHPOINT = "DUPLICATE_DETECTION"

Recommendation = Literal["PASS", "WARN", "SOFT_BLOCK"]


@dataclass(frozen=True, slots=True)
class FuzzyMatch:
    referral_id: UUID
    similarity_score: float
    match_reasons: tuple[str, ...]
    matched_status: str


@dataclass(frozen=True, slots=True)
class FuzzyDuplicateResult:
    recommendation: Recommendation
    similarity_score: float
    matches: tuple[FuzzyMatch, ...] = ()


# ────────────────────────────────────────────────────────────────────
# Normalization helpers.
# ────────────────────────────────────────────────────────────────────
_EMAIL_PLUS_TAG = re.compile(r"\+[^@]+(?=@)")
_PHONE_DIGITS = re.compile(r"\D")


def _normalize_email(email: str) -> str:
    """Lowercase + strip whitespace + drop `+tag` (gmail-style aliases)."""
    cleaned = email.strip().lower()
    cleaned = _EMAIL_PLUS_TAG.sub("", cleaned)
    return cleaned


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_DIGITS.sub("", phone)
    if len(digits) >= 10:
        # Keep last 10 — same number with/without country code matches.
        return digits[-10:]
    return digits or None


def _normalize_name(name: str) -> str:
    """NFKC-normalize unicode, lowercase, collapse whitespace.

    Handles "Riya Sharma" vs "RIYA  Sharma" vs "riya sharma" identically,
    and treats accented characters in regional spellings consistently.
    """
    nfkc = unicodedata.normalize("NFKC", name).strip().lower()
    return " ".join(nfkc.split())


# ────────────────────────────────────────────────────────────────────
# Fuzzy match.
# ────────────────────────────────────────────────────────────────────
async def fuzzy_match(
    session: AsyncSession,
    *,
    candidate_name: str,
    candidate_email: str,
    candidate_phone: str | None,
) -> FuzzyDuplicateResult:
    """Compare against the active + recent-terminal pool.

    Scope: every referral from the last `RESUME_RETENTION_MONTHS` (24m)
    that isn't terminated; per Blueprint §7 AI-4 we look only at non-
    terminal records but include CLOSED so re-applications don't sneak
    through. PAN dedup already covers the active-status case at the DB
    level, so this layer is purely about *catching different PANs that
    still look like the same human*.
    """
    norm_email = _normalize_email(candidate_email)
    norm_phone = _normalize_phone(candidate_phone)
    norm_name = _normalize_name(candidate_name)

    cutoff = datetime.now(UTC) - timedelta(days=30 * RESUME_RETENTION_MONTHS)
    excluded_terminal = (
        ReferralStatus.NDA_DECLINED_REJECTED.value,
        ReferralStatus.NDA_TIMEOUT_REJECTED.value,
        ReferralStatus.HR_REJECTED.value,
        ReferralStatus.CANDIDATE_REJECTED.value,
        ReferralStatus.TERMINATED.value,
    )
    candidates = (
        await session.execute(
            select(Referral)
            .where(
                Referral.created_at >= cutoff,
                Referral.status.notin_(excluded_terminal),
            )
        )
    ).scalars().all()

    matches: list[FuzzyMatch] = []
    for existing in candidates:
        score, reasons = _score_pair(
            existing,
            norm_name=norm_name,
            norm_email=norm_email,
            norm_phone=norm_phone,
        )
        if score >= 0.6:
            matches.append(
                FuzzyMatch(
                    referral_id=existing.id,
                    similarity_score=round(score, 4),
                    match_reasons=tuple(reasons),
                    matched_status=existing.status,
                )
            )

    if not matches:
        return FuzzyDuplicateResult(recommendation="PASS", similarity_score=0.0)

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    top = matches[0]
    rec: Recommendation = "SOFT_BLOCK" if top.similarity_score >= 0.9 else "WARN"

    return FuzzyDuplicateResult(
        recommendation=rec,
        similarity_score=top.similarity_score,
        matches=tuple(matches[:5]),  # top 5 is enough for HR review
    )


def _score_pair(
    existing: Referral,
    *,
    norm_name: str,
    norm_email: str,
    norm_phone: str | None,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if _normalize_email(existing.candidate_email) == norm_email:
        score += 0.6
        reasons.append("email_exact_match")

    existing_norm_phone = _normalize_phone(existing.candidate_phone)
    if norm_phone and existing_norm_phone and existing_norm_phone == norm_phone:
        score += 0.4
        reasons.append("phone_exact_match")

    existing_norm_name = _normalize_name(existing.candidate_name)
    name_sim = JaroWinkler.normalized_similarity(existing_norm_name, norm_name)
    if name_sim >= 0.85:
        score += name_sim * 0.2
        reasons.append(f"name_similar:{round(name_sim, 3)}")

    return min(score, 1.0), reasons


__all__ = [
    "MODEL_TOUCHPOINT",
    "FuzzyDuplicateResult",
    "FuzzyMatch",
    "Recommendation",
    "fuzzy_match",
]
