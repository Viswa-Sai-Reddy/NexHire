"""Server-side enforcement of all eligibility rules + the PAN decision
tree (F-40). Pure logic — never trust the client.

Each public function maps to one rule from the Blueprint:
  validate_year_of_study   → RULE-E1
  check_college_cap        → RULE-E2 (returns count + warn/block result)
  validate_referrer_mentor → RULE-E3
  require_unpaid_consent   → RULE-E4
  require_inperson_ready   → RULE-E5
  validate_mentor_capacity → RULE-M-CAP (live, against current threshold)
  validate_dates           → end > start, 4–26 weeks (decision A13)

The PAN decision tree (`pan_check`) returns a structured verdict
mirroring F-40:
  CLEAR | HARD_BLOCK | COOLING_BLOCK | WARN | SOFT_BLOCK
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral import college_repository, cooling_period_service, pan_crypto
from app.modules.referral.cooling_period_service import CoolingStatus
from app.modules.referral.models import MentorThresholdConfig, Referral
from app.shared.constants import (
    ALLOWED_YEARS_OF_STUDY,
    INTERNSHIP_MAX_DAYS,
    INTERNSHIP_MIN_DAYS,
    MAX_REFERRALS_PER_REFERRER_PER_COLLEGE,
    ReferralStatus,
)
from app.shared.exceptions import (
    CoolingPeriodActiveError,
    DuplicateCandidateBlockedError,
    GraduatedStudentIneligibleError,
    InpersonReadyRequiredError,
    InvalidDateRangeError,
    InvalidStartDatePastError,
    InvalidYearOfStudyError,
    MentorAtCapacityError,
    ReferrerIsMentorError,
    UnpaidConsentRequiredError,
)

logger = logging.getLogger("nexhire.validator")


# ────────────────────────────────────────────────────────────────────
# Eligibility rules — synchronous, no DB.
# ────────────────────────────────────────────────────────────────────
def validate_year_of_study(year: int, *, graduation_year: int, current_year: int) -> None:
    """RULE-E1.

    Allowed: 2nd, 3rd, 4th year. Blocks: 1st year + students whose
    `graduation_year ≤ current_year` (already graduated).
    """
    if year not in ALLOWED_YEARS_OF_STUDY:
        raise InvalidYearOfStudyError()
    if graduation_year <= current_year:
        raise GraduatedStudentIneligibleError()


def validate_referrer_mentor(*, referrer_id: UUID, mentor_id: UUID | None) -> None:
    """RULE-E3."""
    if mentor_id is not None and referrer_id == mentor_id:
        raise ReferrerIsMentorError()


def require_unpaid_consent(unpaid_consent: bool) -> None:
    """RULE-E4."""
    if not unpaid_consent:
        raise UnpaidConsentRequiredError()


def require_inperson_ready(inperson_ready: bool) -> None:
    """RULE-E5."""
    if not inperson_ready:
        raise InpersonReadyRequiredError()


def validate_dates(*, start: date, end: date, today: date) -> None:
    """end > start; start ≥ today; duration in [28, 182] days (A13)."""
    if start < today:
        raise InvalidStartDatePastError()
    if end <= start:
        raise InvalidDateRangeError()
    span = (end - start).days
    if span < INTERNSHIP_MIN_DAYS or span > INTERNSHIP_MAX_DAYS:
        raise InvalidDateRangeError(
            user_message=(
                f"Internship duration must be between {INTERNSHIP_MIN_DAYS // 7} "
                f"and {INTERNSHIP_MAX_DAYS // 7} weeks."
            ),
            details={"days": span, "min": INTERNSHIP_MIN_DAYS, "max": INTERNSHIP_MAX_DAYS},
        )


# ────────────────────────────────────────────────────────────────────
# Async rules — need DB.
# ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class CollegeCapResult:
    college_id: UUID
    used: int
    limit: int = MAX_REFERRALS_PER_REFERRER_PER_COLLEGE

    @property
    def can_submit(self) -> bool:
        return self.used < self.limit

    @property
    def warning(self) -> bool:
        return self.used == self.limit - 1

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


async def check_college_cap(
    session: AsyncSession,
    *,
    referrer_id: UUID,
    college_id: UUID,
) -> CollegeCapResult:
    """RULE-E2.

    Returns the current count + a result object. Doesn't raise — UI
    needs the count for the `1/2 used` advisory. The submission path
    raises `CollegeCapExceededError` only when `used >= limit`.
    """
    used = await college_repository.get_active_referral_count(
        session, referrer_id=referrer_id, college_id=college_id
    )
    return CollegeCapResult(college_id=college_id, used=used)


async def validate_mentor_capacity(
    session: AsyncSession,
    *,
    mentor_id: UUID,
) -> None:
    """RULE-M-CAP.

    Reads the live mentor threshold (S25-configurable; decision §20.5
    promises new assignments use the *current* value). Active mentees
    counted from `referrals` rows still in non-terminal status with
    this mentor and `status` past MENTOR_ACCEPTED.
    """
    threshold_row = (
        await session.execute(
            select(MentorThresholdConfig).where(
                MentorThresholdConfig.is_current.is_(True)
            )
        )
    ).scalar_one()
    threshold = threshold_row.max_mentees

    active_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM referrals
                WHERE mentor_id = :m
                  AND status IN (
                      'MENTOR_ACCEPTED','HR_REVIEW','APPROVED',
                      'JOINING_FORM_PENDING','JOINING_FORM_SUBMITTED',
                      'JOINING_FORM_LOCKED','ID_PENDING','ID_ISSUED',
                      'NDA_PENDING','NDA_SIGNED','ACCESS_PENDING',
                      'ACTIVE','EXTENDED','CLOSURE_PENDING'
                  )
                """
            ).bindparams(m=mentor_id)
        )
    ).scalar_one()

    if int(active_count) >= int(threshold):
        # Resolve a name for the error message in one extra query — small
        # cost, much friendlier UX.
        name = (
            await session.execute(
                text("SELECT full_name FROM users WHERE id = :m").bindparams(m=mentor_id)
            )
        ).scalar_one_or_none()
        raise MentorAtCapacityError(mentor_name=name or "This mentor")


# ────────────────────────────────────────────────────────────────────
# PAN check — F-40 decision tree.
#   STEP 1: active duplicate (hard block)
#   STEP 2: cooling period (cooling block)
#   STEP 3: fuzzy duplicate (warn / soft block)   ← S1.4 plugs in
#   STEP 4: clear
# ────────────────────────────────────────────────────────────────────
PanVerdict = Literal["CLEAR", "HARD_BLOCK", "COOLING_BLOCK", "WARN", "SOFT_BLOCK"]


@dataclass(frozen=True, slots=True)
class PanCheckResult:
    verdict: PanVerdict
    pan_hash: str
    pan_masked: str
    message: str
    existing_referral_id: UUID | None = None
    existing_status: str | None = None
    cooling: CoolingStatus | None = None
    similarity_score: float | None = None
    match_reasons: tuple[str, ...] = ()
    allow_override: bool = False


async def pan_check(
    session: AsyncSession,
    *,
    pan_plain: str,
) -> PanCheckResult:
    """Run the PAN dedup decision tree.

    Steps 1–2 are deterministic. Step 3 (fuzzy match by name+email+phone)
    is delegated to the AI module's duplicate detector once we have a
    candidate name/email; for the realtime "user typed PAN" call we
    only do steps 1–2 here.

    Caller must pass plaintext PAN — we hash it inside this function.
    """
    pan_hash = pan_crypto.hash_for_lookup(pan_plain)
    pan_masked = pan_crypto.mask(pan_plain)

    # ── STEP 1: Active duplicate ──────────────────────────────────
    active_statuses = [
        s.value for s in ReferralStatus if s.value not in {
            ReferralStatus.CLOSED.value,
            ReferralStatus.HR_REJECTED.value,
            ReferralStatus.CANDIDATE_REJECTED.value,
            ReferralStatus.NDA_TIMEOUT_REJECTED.value,
            ReferralStatus.NDA_DECLINED_REJECTED.value,
            ReferralStatus.TERMINATED.value,
        }
    ]
    active = (
        await session.execute(
            select(Referral)
            .where(
                Referral.candidate_pan_hash == pan_hash,
                Referral.status.in_(active_statuses),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is not None:
        return PanCheckResult(
            verdict="HARD_BLOCK",
            pan_hash=pan_hash,
            pan_masked=pan_masked,
            message=(
                f"An active referral already exists for this candidate "
                f"(Status: {active.status})."
            ),
            existing_referral_id=active.id,
            existing_status=active.status,
            allow_override=False,
        )

    # ── STEP 2: Cooling period ────────────────────────────────────
    cooling = await cooling_period_service.get_status(session, pan_hash=pan_hash)
    if cooling.is_in_cooling:
        return PanCheckResult(
            verdict="COOLING_BLOCK",
            pan_hash=pan_hash,
            pan_masked=pan_masked,
            message=_cooling_message(cooling),
            cooling=cooling,
            allow_override=cooling.terminal_state != ReferralStatus.CLOSED.value,
        )

    # ── STEP 3 (fuzzy) is delegated; the realtime endpoint stops here.
    return PanCheckResult(
        verdict="CLEAR",
        pan_hash=pan_hash,
        pan_masked=pan_masked,
        message="PAN verified — no existing referral or cooling period found.",
    )


def _cooling_message(cooling: CoolingStatus) -> str:
    labels = {
        ReferralStatus.NDA_DECLINED_REJECTED.value: "explicitly declined the NDA",
        ReferralStatus.TERMINATED.value: "left mid-internship",
        ReferralStatus.NDA_TIMEOUT_REJECTED.value: "did not sign the NDA within the deadline",
        ReferralStatus.HR_REJECTED.value: "was found unfit during HR review",
        ReferralStatus.CLOSED.value: "completed a previous internship",
    }
    why = labels.get(cooling.terminal_state or "", "had a previous referral closed")
    return (
        f"This candidate {why}. A {cooling.months_duration}-month cooling "
        f"period applies until {cooling.cooling_end}."
    )


# ────────────────────────────────────────────────────────────────────
# Convenience: convert PanCheckResult to a raised exception when the
# caller wants a hard guard (e.g. submission path).
# ────────────────────────────────────────────────────────────────────
def raise_if_blocked(result: PanCheckResult) -> None:
    if result.verdict == "HARD_BLOCK":
        raise DuplicateCandidateBlockedError(
            details={
                "pan_masked": result.pan_masked,
                "existing_referral_id": str(result.existing_referral_id),
                "existing_status": result.existing_status,
            }
        )
    if result.verdict == "COOLING_BLOCK" and result.cooling is not None:
        raise CoolingPeriodActiveError(
            terminal_state=result.cooling.terminal_state or "",
            ends_on=str(result.cooling.cooling_end),
            days_remaining=result.cooling.days_remaining or 0,
        )
