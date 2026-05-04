"""Domain events — shared kernel.

Cross-module communication is event-driven (Blueprint §8.2 Rule 1):
modules publish events; other modules subscribe. The shared kernel
defines the event *types* but never their *handlers* — that keeps the
kernel a pure contract layer.

Conventions:
  * Every event is an immutable, frozen dataclass.
  * Every event subclasses `DomainEvent` and inherits `event_id`,
    `occurred_at`, `correlation_id` automatically.
  * Field names mirror the canonical column names so handlers can be
    fed directly from repository rows.

Only events for S0–S1 are listed below. Later slices append more events
in this file (mentor lifecycle, NDA, extension, closure, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.shared.value_objects import (
    InternId,
    MentorAssignmentId,
    ReferralId,
    UserId,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Base class for all domain events.

    `event_id` and `occurred_at` are auto-set; `correlation_id` is set
    by the publishing service so a tree of follow-on events is traceable
    to the originating user request.
    """

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)
    correlation_id: UUID | None = None

    @property
    def event_type(self) -> str:
        """Used as the persisted name in `outbox_events.event_type` and
        `audit_events.event_type`.
        """
        return type(self).__name__


# ────────────────────────────────────────────────────────────
# S0 — health check / smoke (used by tests).
# ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class Heartbeat(DomainEvent):
    """Test-only event used by S0 acceptance tests to verify the bus."""

    note: str = "ping"


# ────────────────────────────────────────────────────────────
# S0 — auth events.
# ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class UserLoggedIn(DomainEvent):
    user_id: UserId
    role: str
    ip_address: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UserCreated(DomainEvent):
    user_id: UserId
    email: str
    role: str
    azure_oid: str | None = None


# ────────────────────────────────────────────────────────────
# S1 — referral lifecycle (subset that S1 emits/consumes).
# Additional events for mentor/HR/AI flows are added in later slices.
# ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralSubmitted(DomainEvent):
    referral_id: ReferralId
    referrer_id: UserId
    candidate_email: str
    candidate_name: str
    selected_mentor_id: UserId
    college_id: UUID
    pan_masked: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MentorAssignmentRequested(DomainEvent):
    """Triggers the mentor-assignment notification email and the 3-day
    timeout job. Emitted by [referral] after [mentor] persists the
    assignment row.
    """

    referral_id: ReferralId
    mentor_id: UserId
    assignment_id: MentorAssignmentId
    attempt_number: int
    accept_token: str   # raw; only present in-memory for the email handler
    reject_token: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeAnalyzed(DomainEvent):
    """Emitted after AI-1 finishes parsing a resume."""

    referral_id: ReferralId
    parse_result_id: UUID
    succeeded: bool
    confidence_min: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateUserCreated(DomainEvent):
    """Decision A5: candidates get a `users` row. Emitted by [auth] when
    HR approves a referral and the magic-link service provisions the
    candidate's user row + first magic link.
    """

    user_id: UserId
    intern_id: InternId
    referral_id: ReferralId
    candidate_email: str


# ────────────────────────────────────────────────────────────
# S2 — Mentor lifecycle + HR auto-approval.
# ────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True, kw_only=True)
class MentorAccepted(DomainEvent):
    """Mentor clicked Accept. Triggers the auto-approval engine."""

    referral_id: ReferralId
    mentor_id: UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class MentorRejected(DomainEvent):
    referral_id: ReferralId
    mentor_id: UserId
    attempt_number: int
    reason: str
    is_terminal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class MentorTimedOut(DomainEvent):
    referral_id: ReferralId
    mentor_id: UserId
    attempt_number: int
    is_terminal: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralAutoApproved(DomainEvent):
    """F-35 clean path. The candidate magic link (S3) subscribes to this."""

    referral_id: ReferralId
    candidate_email: str
    candidate_name: str
    recall_until: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralRoutedToHr(DomainEvent):
    """F-35 flagged path. The HR-task auto-router has already created
    the task; this event lets notification handlers nudge the assigned
    HR member.
    """

    referral_id: ReferralId
    flags: tuple[str, ...]
    hr_recommendation: str
    assigned_hr_id: UserId


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralApproved(DomainEvent):
    """HR (or auto-approval) approved the referral. Subscribed to by
    [auth] in S3 to provision the candidate user + magic link.
    """

    referral_id: ReferralId
    candidate_email: str
    candidate_name: str
    approved_by_user_id: UserId
    approved_by_label: str  # "HR" | "AI_AUTO_APPROVAL"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralHrRejected(DomainEvent):
    referral_id: ReferralId
    rejected_by_user_id: UserId
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralCorrectionRequested(DomainEvent):
    referral_id: ReferralId
    requested_by_user_id: UserId
    notes: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoApprovalRecalled(DomainEvent):
    referral_id: ReferralId
    recalled_by_user_id: UserId
    recall_reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MentorReassigned(DomainEvent):
    """A14: HR mid-flow reassignment without resetting the strike counter."""

    referral_id: ReferralId
    original_mentor_id: UserId
    new_mentor_id: UserId
    hr_actor_id: UserId
    reason: str
