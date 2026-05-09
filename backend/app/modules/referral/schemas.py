"""Pydantic schemas for the referral HTTP surface.

Schemas mirror the 5-step form (Blueprint §6 + UI sample):
  Step 1: Candidate basics + PAN
  Step 2: Eligibility confirmations + AI risk advisory
  Step 3: Mentor selection
  Step 4: Internship details
  Step 5: Review

The submission payload (`ReferralSubmitRequest`) is the union of all
five steps. Drafts (sent via PATCH while the user types) use the same
shape with everything optional via `model_partial=True`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ────────────────────────────────────────────────────────────────────
# Submit request.
# ────────────────────────────────────────────────────────────────────
class ReferralSubmitRequest(BaseModel):
    # Step 1
    candidate_name: str = Field(..., min_length=2, max_length=255)
    candidate_email: EmailStr
    candidate_phone: str | None = Field(None, max_length=20)
    candidate_pan: str = Field(..., pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    college_id: UUID
    candidate_year_of_study: int = Field(..., ge=2, le=4)
    candidate_graduation_year: int = Field(..., ge=2025, le=2035)

    # Step 2
    unpaid_consent: bool
    inperson_ready: bool
    relationship_declaration: str | None = Field(None, max_length=50)
    relationship_declaration_detail: str | None = None

    # Step 3
    mentor_id: UUID

    # Step 4
    project_title: str = Field(..., min_length=3, max_length=255)
    project_overview: str | None = Field(None, max_length=2_000)
    joining_location: str = Field(..., min_length=2, max_length=255)
    internship_start_date: date
    internship_end_date: date

    # Step 1 extra — points to a previously-uploaded resume (from the
    # /referrals/upload-resume endpoint). Optional because draft saves
    # may precede the upload.
    resume_document_id: UUID | None = None

    @field_validator("candidate_pan")
    @classmethod
    def _normalize_pan(cls, value: str) -> str:
        return value.strip().upper()


# ────────────────────────────────────────────────────────────────────
# Realtime PAN check (F-40).
# ────────────────────────────────────────────────────────────────────
class PanCheckRequest(BaseModel):
    pan: str = Field(..., pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")

    @field_validator("pan")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().upper()


class PanCheckResponse(BaseModel):
    verdict: Literal["CLEAR", "HARD_BLOCK", "COOLING_BLOCK", "WARN", "SOFT_BLOCK"]
    pan_masked: str
    message: str
    existing_referral_id: UUID | None = None
    existing_status: str | None = None
    cooling_end: date | None = None
    cooling_days_remaining: int | None = None
    cooling_terminal_state: str | None = None
    months_duration: int | None = None
    allow_override: bool = False


# ────────────────────────────────────────────────────────────────────
# Resume upload + AI prefill.
# ────────────────────────────────────────────────────────────────────
class ResumePrefillResponse(BaseModel):
    """Returned by POST /referrals/upload-resume.

    The form uses these to populate the wizard with confidence badges.
    `document_id` is the persisted blob reference the form should pass
    back to /referrals on submit so we re-link rather than re-upload.
    """

    document_id: UUID
    succeeded: bool
    user_message: str | None = None
    degradation_reason: str | None = None

    candidate_name: str | None = None
    candidate_name_confidence: float | None = None
    candidate_email: str | None = None
    candidate_email_confidence: float | None = None
    candidate_phone: str | None = None
    candidate_phone_confidence: float | None = None
    candidate_year_of_study: int | None = None
    candidate_year_of_study_confidence: float | None = None
    college_name: str | None = None
    college_name_confidence: float | None = None
    candidate_graduation_year: int | None = None
    candidate_graduation_year_confidence: float | None = None

    skills: list[str] = Field(default_factory=list)
    suggested_project_tracks: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    recommended_mentor_questions: list[str] = Field(default_factory=list)
    internship_readiness_score: int = 0


# ────────────────────────────────────────────────────────────────────
# Read shapes.
# ────────────────────────────────────────────────────────────────────
class CollegeCapStatus(BaseModel):
    college_id: UUID
    used: int
    limit: int
    remaining: int
    can_submit: bool
    warning: bool


class ReferralSummary(BaseModel):
    id: UUID
    status: str
    current_stage: str
    candidate_name: str
    candidate_email: str  # response only — not re-validated
    pan_masked: str
    college_id: UUID
    project_title: str | None = None
    submitted_at: datetime | None = None
    mentor_id: UUID | None = None
    mentor_attempt_count: int
    created_at: datetime
    # Populated once the referral has been approved and an Intern row
    # exists. Lets the caller drive lifecycle actions (e.g. terminate).
    intern_id: UUID | None = None
    intern_status: str | None = None


class ReferralDetail(ReferralSummary):
    candidate_phone: str | None = None
    candidate_year_of_study: int
    candidate_graduation_year: int
    project_overview: str | None = None
    joining_location: str | None = None
    internship_start_date: date | None = None
    internship_end_date: date | None = None
    rejection_reason: str | None = None


class ReferralSubmitResponse(BaseModel):
    referral_id: UUID
    status: str
    risk_score: int
    risk_classification: Literal["LOW", "MEDIUM", "HIGH"]
    duplicate_warning: str | None = None


# ────────────────────────────────────────────────────────────────────
# College autocomplete.
# ────────────────────────────────────────────────────────────────────
class CollegeSearchResult(BaseModel):
    id: UUID
    canonical_name: str
    aliases: list[str]
    location_state: str | None = None
    type: str | None = None


# ────────────────────────────────────────────────────────────────────
# Mentor picker — basic flat list (S1 fallback) and AI-2 ranked
# suggestions (S2 default) live side-by-side.
# ────────────────────────────────────────────────────────────────────
class MentorPickerEntry(BaseModel):
    user_id: UUID
    full_name: str
    # Internal email — return as plain str so reserved-domain placeholders
    # (e.g. ai-system@nexhire.internal) don't trip EmailStr re-validation
    # on the response path.
    email: str
    active_mentees: int
    threshold: int
    available: bool


class MentorPickerResponse(BaseModel):
    threshold: int
    mentors: list[MentorPickerEntry]


class MentorRadar(BaseModel):
    skill: int = Field(..., ge=0, le=20)
    availability: int = Field(..., ge=0, le=20)
    reputation: int = Field(..., ge=0, le=20)
    familiarity: int = Field(..., ge=0, le=20)
    responsiveness: int = Field(..., ge=0, le=20)


class MentorSuggestion(BaseModel):
    user_id: UUID
    full_name: str
    email: str  # see MentorPickerEntry note
    active_mentees: int
    threshold: int
    match_score: int = Field(..., ge=0, le=100)
    radar: MentorRadar
    reason: str
    ai_reason: bool


class MentorSuggestRequest(BaseModel):
    college_id: UUID
    candidate_skills: list[str] = Field(default_factory=list)
    excluded_mentor_ids: list[UUID] = Field(default_factory=list)
    top_n: int = Field(default=3, ge=1, le=10)


class MentorSuggestResponse(BaseModel):
    threshold: int
    suggestions: list[MentorSuggestion]
