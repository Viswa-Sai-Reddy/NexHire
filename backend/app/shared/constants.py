"""Domain constants — shared kernel.

These enums are the single source of truth for user roles, referral status,
NDA status, and other domain-wide values. Postgres enum types are generated
from these in Alembic migrations; Pydantic schemas reference them directly.

CHANGES TO ANY ENUM REQUIRE:
  1. A code change here.
  2. A new Alembic migration (`ALTER TYPE ... ADD VALUE`).
  3. An ADR if the change is non-trivial.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

# ────────────────────────────────────────────────────────────
# Reserved system actor (decision A2).
# Auto-actions performed by NexHire AI use this as actor_user_id.
# Seeded by Alembic migration; UUID is fixed so the value is identical
# across environments (the constant equals the row that exists in the
# users table).
# ────────────────────────────────────────────────────────────
AI_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
AI_SYSTEM_EMAIL = "ai-system@nexhire.internal"
AI_SYSTEM_FULL_NAME = "NexHire AI"


# ────────────────────────────────────────────────────────────
# User roles (decisions A2, A4, A5).
# SYSTEM is the reserved AI actor and grants no human RBAC permissions.
# CANDIDATE rows are auto-created on referral approval (A5).
# ────────────────────────────────────────────────────────────
class UserRole(StrEnum):
    REFERRER = "REFERRER"
    MENTOR = "MENTOR"
    HR = "HR"
    IT_AD = "IT_AD"
    ADMIN = "ADMIN"
    PROGRAM_OWNER = "PROGRAM_OWNER"
    CANDIDATE = "CANDIDATE"
    SYSTEM = "SYSTEM"


HUMAN_ROLES: frozenset[UserRole] = frozenset(
    r for r in UserRole if r is not UserRole.SYSTEM
)
EMPLOYEE_ROLES: frozenset[UserRole] = frozenset(
    {
        UserRole.REFERRER,
        UserRole.MENTOR,
        UserRole.HR,
        UserRole.IT_AD,
        UserRole.ADMIN,
        UserRole.PROGRAM_OWNER,
    }
)


# ────────────────────────────────────────────────────────────
# Referral status — decision A6 (locked).
# Order does not imply progression; see ReferralStatus state machine
# in app/modules/workflow/state_machine.py.
# ────────────────────────────────────────────────────────────
class ReferralStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    MENTOR_PENDING = "MENTOR_PENDING"
    MENTOR_ACCEPTED = "MENTOR_ACCEPTED"
    MENTOR_REJECTED = "MENTOR_REJECTED"          # transient
    MENTOR_TIMED_OUT = "MENTOR_TIMED_OUT"        # transient
    HR_REVIEW = "HR_REVIEW"                      # only flagged cases (A1)
    CORRECTION_NEEDED = "CORRECTION_NEEDED"
    APPROVED = "APPROVED"
    JOINING_FORM_PENDING = "JOINING_FORM_PENDING"
    JOINING_FORM_SUBMITTED = "JOINING_FORM_SUBMITTED"
    JOINING_FORM_LOCKED = "JOINING_FORM_LOCKED"
    ID_PENDING = "ID_PENDING"
    ID_ISSUED = "ID_ISSUED"
    NDA_PENDING = "NDA_PENDING"
    NDA_SIGNED = "NDA_SIGNED"
    ACCESS_PENDING = "ACCESS_PENDING"
    ACTIVE = "ACTIVE"
    EXTENDED = "EXTENDED"
    CLOSURE_PENDING = "CLOSURE_PENDING"
    # Terminal states
    CLOSED = "CLOSED"
    HR_REJECTED = "HR_REJECTED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"
    NDA_TIMEOUT_REJECTED = "NDA_TIMEOUT_REJECTED"
    NDA_DECLINED_REJECTED = "NDA_DECLINED_REJECTED"
    TERMINATED = "TERMINATED"


TERMINAL_REFERRAL_STATUSES: frozenset[ReferralStatus] = frozenset(
    {
        ReferralStatus.CLOSED,
        ReferralStatus.HR_REJECTED,
        ReferralStatus.CANDIDATE_REJECTED,
        ReferralStatus.NDA_TIMEOUT_REJECTED,
        ReferralStatus.NDA_DECLINED_REJECTED,
        ReferralStatus.TERMINATED,
    }
)
# States that count as "active duplicate" for PAN dedup (F-33, F-40 step 1).
ACTIVE_REFERRAL_STATUSES: frozenset[ReferralStatus] = frozenset(
    s for s in ReferralStatus if s not in TERMINAL_REFERRAL_STATUSES
)
# Cooling-period-bearing states (RULE-CP1..CP6).
COOLING_TRIGGER_STATES: frozenset[ReferralStatus] = frozenset(
    {
        ReferralStatus.NDA_DECLINED_REJECTED,   # 6m
        ReferralStatus.TERMINATED,              # 6m
        ReferralStatus.NDA_TIMEOUT_REJECTED,    # 3m
        ReferralStatus.HR_REJECTED,             # 3m
        ReferralStatus.CANDIDATE_REJECTED,      # 0m (no cooling)
        ReferralStatus.CLOSED,                  # 3m re-join spacing
    }
)


# ────────────────────────────────────────────────────────────
# Mentor assignment status (RULE-M1..M4 + decision A14).
# ────────────────────────────────────────────────────────────
class MentorAssignmentStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    REASSIGNED = "REASSIGNED"   # decision A14: HR replaced this mentor mid-flow


# ────────────────────────────────────────────────────────────
# NDA status (RULE-N1..N4).
# ────────────────────────────────────────────────────────────
class NdaStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    SIGNED = "SIGNED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


# ────────────────────────────────────────────────────────────
# Joining form lifecycle.
# ────────────────────────────────────────────────────────────
class JoiningFormStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    LOCKED = "LOCKED"


# ────────────────────────────────────────────────────────────
# Intern lifecycle (joins referral status; tracks the post-approval entity).
# ────────────────────────────────────────────────────────────
class InternStatus(StrEnum):
    PENDING = "PENDING"
    ACCESS_PENDING = "ACCESS_PENDING"
    ACTIVE = "ACTIVE"
    EXTENDED = "EXTENDED"
    CLOSURE_PENDING = "CLOSURE_PENDING"
    CLOSED = "CLOSED"
    TERMINATED = "TERMINATED"


# ────────────────────────────────────────────────────────────
# Active Directory provisioning state for the intern's AD account.
# ────────────────────────────────────────────────────────────
class AdAccountStatus(StrEnum):
    NOT_CREATED = "NOT_CREATED"
    PROVISIONING = "PROVISIONING"
    PROVISIONED = "PROVISIONED"   # created but not yet enabled
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


# ────────────────────────────────────────────────────────────
# Tasks (Non-Worker ID, AD provisioning, badge access, certificate, ...).
# ────────────────────────────────────────────────────────────
class TaskType(StrEnum):
    NON_WORKER_ID = "NON_WORKER_ID"      # legacy path; AI auto-generates per F-34
    NDA_SIGN = "NDA_SIGN"
    AD_PROVISION = "AD_PROVISION"
    BADGE_ACCESS = "BADGE_ACCESS"
    AD_DEACTIVATE = "AD_DEACTIVATE"
    BADGE_DEACTIVATE = "BADGE_DEACTIVATE"
    CERT_REQUEST = "CERT_REQUEST"
    HR_REVIEW = "HR_REVIEW"
    JOINING_FORM_REVIEW = "JOINING_FORM_REVIEW"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


# ────────────────────────────────────────────────────────────
# Action token kinds (decisions: B12, E12).
# Backed by `action_tokens.action_type` enum.
# ────────────────────────────────────────────────────────────
class ActionTokenType(StrEnum):
    MENTOR_RESPONSE = "MENTOR_RESPONSE"
    CANDIDATE_ACCESS = "CANDIDATE_ACCESS"
    RECALL_AUTO_ACTION = "RECALL_AUTO_ACTION"
    EXTENSION_RESPONSE = "EXTENSION_RESPONSE"


# ────────────────────────────────────────────────────────────
# Document types (decision E8).
# ────────────────────────────────────────────────────────────
class DocumentType(StrEnum):
    RESUME = "RESUME"
    ID_PROOF = "ID_PROOF"
    EDUCATION_CERT = "EDUCATION_CERT"
    NDA_TEMPLATE = "NDA_TEMPLATE"
    SIGNED_NDA = "SIGNED_NDA"
    OFFER_LETTER = "OFFER_LETTER"
    CERTIFICATE = "CERTIFICATE"
    PHOTO = "PHOTO"
    PAN_CARD = "PAN_CARD"
    OTHER = "OTHER"


# ────────────────────────────────────────────────────────────
# Notification template IDs — Blueprint §6 + §19 + decision A15/A17.
# ────────────────────────────────────────────────────────────
class NotificationTemplate(StrEnum):
    REFERRAL_CONFIRMATION = "NOTIF_001_REFERRAL_CONFIRMATION"
    MENTOR_ASSIGNMENT = "NOTIF_002_MENTOR_ASSIGNMENT"
    NDA_ISSUANCE = "NOTIF_003_NDA_ISSUANCE"
    MENTOR_REJECTION_TO_REFERRER = "NOTIF_004_MENTOR_REJECTION_TO_REFERRER"
    MENTOR_TIMEOUT_TO_REFERRER = "NOTIF_005_MENTOR_TIMEOUT_TO_REFERRER"
    CONGRATULATIONS_TO_CANDIDATE = "NOTIF_006_CONGRATULATIONS_TO_CANDIDATE"
    CERTIFICATE_DELIVERY = "NOTIF_007_CERTIFICATE_DELIVERY"
    CLOSURE_REMINDER = "NOTIF_008_CLOSURE_REMINDER"
    NDA_FINAL_WARNING = "NOTIF_009_NDA_FINAL_WARNING"
    OFFER_LETTER = "NOTIF_010_OFFER_LETTER"
    OFFER_LETTER_FYI_HR = "NOTIF_011_OFFER_LETTER_FYI_HR"
    CERT_AUTO_SENT_FYI = "NOTIF_012_CERT_AUTO_SENT_FYI"
    COOLING_OVERRIDE_HR = "NOTIF_013_COOLING_OVERRIDE_HR"
    COOLING_PERIOD_APPLIED = "NOTIF_014_COOLING_PERIOD_APPLIED"
    COOLING_ENDING_SOON = "NOTIF_015_COOLING_ENDING_SOON"
    COOLING_EXPIRED = "NOTIF_016_COOLING_EXPIRED"
    OFFER_LETTER_RECALLED = "NOTIF_017_OFFER_LETTER_RECALLED"
    NDA_TIMEOUT_CANDIDATE = "NOTIF_018_NDA_TIMEOUT_CANDIDATE"
    NDA_DECLINED_CANDIDATE = "NOTIF_019_NDA_DECLINED_CANDIDATE"
    MAX_MENTOR_CANDIDATE = "NOTIF_020_MAX_MENTOR_CANDIDATE"
    HR_REJECTED_CANDIDATE = "NOTIF_021_HR_REJECTED_CANDIDATE"
    JOINING_FORM_INVITE = "NOTIF_022_JOINING_FORM_INVITE"


# ────────────────────────────────────────────────────────────
# Eligibility / business-rule constants.
# ────────────────────────────────────────────────────────────
ALLOWED_YEARS_OF_STUDY: frozenset[int] = frozenset({2, 3, 4})         # RULE-E1
MAX_REFERRALS_PER_REFERRER_PER_COLLEGE = 2                            # RULE-E2 (BRD-locked)
MAX_MENTOR_ATTEMPTS = 3                                                # RULE-M3
DEFAULT_MENTOR_THRESHOLD = 4                                           # configurable (S25)
NDA_DEADLINE_DAYS = 5                                                  # RULE-N1
MENTOR_RESPONSE_DEADLINE_DAYS = 3                                      # RULE-M1
MAGIC_LINK_EXPIRY_HOURS = 72                                           # F-03
ACTION_TOKEN_EXPIRY_DAYS = 3                                           # F-23
JWT_ACCESS_TTL_SECONDS = 28_800                                        # 8h
JWT_REFRESH_TTL_SECONDS = 86_400                                       # 24h
RESUME_RETENTION_MONTHS = 24                                           # decision E16
INTERNSHIP_MIN_DAYS = 28                                               # decision A13 — 4 weeks
INTERNSHIP_MAX_DAYS = 182                                              # decision A13 — 26 weeks
EXTENSION_MAX_COUNT = 2                                                # decision A16
EXTENSION_MAX_DAYS = 28                                                # decision A16

# Cooling-period defaults (Blueprint §19; configurable by Program Owner).
DEFAULT_COOLING_MONTHS: dict[str, int] = {
    ReferralStatus.NDA_DECLINED_REJECTED: 6,
    ReferralStatus.TERMINATED: 6,
    ReferralStatus.NDA_TIMEOUT_REJECTED: 3,
    ReferralStatus.HR_REJECTED: 3,
    ReferralStatus.CANDIDATE_REJECTED: 0,
    ReferralStatus.CLOSED: 3,
}

COOLING_OVERRIDE_MIN_REASON_LENGTH = 50  # RULE-CP7

# File upload constraints (decisions B22 + spec).
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_JOINING_FORM = 8
ALLOWED_UPLOAD_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
    }
)


# ────────────────────────────────────────────────────────────
# Audit (Blueprint §9.1, §17.12).
# `pg_advisory_xact_lock` key for serializing the checksum chain.
# ────────────────────────────────────────────────────────────
AUDIT_CHAIN_LOCK_KEY = 9_812_345_678  # arbitrary, fixed across processes
GENESIS_CHECKSUM = "GENESIS"


# ────────────────────────────────────────────────────────────
# Stage palette (Implementation_Plan.md → UI Design Reference).
# Mirrors `frontend/tailwind.config.ts` `theme.extend.colors.stage`.
# Used by backend when emitting stage-tagged data for charts.
# ────────────────────────────────────────────────────────────
STAGE_PALETTE: dict[str, str] = {
    "submitted": "blue-500",
    "review": "amber-500",
    "onboarding": "indigo-500",
    "nda": "violet-500",
    "active": "emerald-500",
    "extended": "teal-500",
    "closure": "slate-500",
    "rejected": "rose-500",
}
