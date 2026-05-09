"""Referral-domain ORM models.

One file for the whole referral aggregate (Referral + MentorAssignment
+ ReferralStageHistory + AI result tables). Splitting into separate
files would obscure the natural cohesion: every read and write touches
the referral row plus its satellites.

Models are dataclass-style via `MappedAsDataclass` (Base in
infrastructure.database). All datetimes are TIMESTAMPTZ; all UUIDs are
Postgres-native UUIDs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


# ────────────────────────────────────────────────────────────────────
# Reference tables (configuration, master data).
# ────────────────────────────────────────────────────────────────────
class CoolingPeriodConfig(Base):
    """One row per terminal state. Editable by Program Owner via S25."""

    __tablename__ = "cooling_period_config"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    terminal_state: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    duration_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    set_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    previous_value: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class MentorThresholdConfig(Base):
    """At any moment exactly one row has `is_current = true`."""

    __tablename__ = "mentor_threshold_config"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    max_mentees: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=4, server_default=text("4")
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    set_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class Holiday(Base):
    """Per-day calendar entry consulted by the business-day calculator."""

    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="NATIONAL", server_default=text("'NATIONAL'")
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    created_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    template_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class College(Base):
    """Master college list (decision A7)."""

    __tablename__ = "colleges"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    location_state: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )
    type: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


# ────────────────────────────────────────────────────────────────────
# Document — minimal model, expanded in S3 (joining-form uploads).
# ────────────────────────────────────────────────────────────────────
class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    azure_blob_container: Mapped[str] = mapped_column(String(255), nullable=False)
    azure_blob_key: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_recalled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recalled_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    retention_delete_at: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )


# ────────────────────────────────────────────────────────────────────
# Referral — the core entity.
# ────────────────────────────────────────────────────────────────────
class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    referrer_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mentor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        default=None,
    )

    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_email: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    college_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("colleges.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_year_of_study: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    candidate_graduation_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # PAN — see pan_crypto.py for the contract.
    candidate_pan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_pan_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    candidate_pan_masked: Mapped[str] = mapped_column(String(20), nullable=False)

    project_title: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    project_overview: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    joining_location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    internship_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    internship_end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    relationship_declaration: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    relationship_declaration_detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    unpaid_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    inperson_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="DRAFT", server_default=text("'DRAFT'")
    )
    current_stage: Mapped[str] = mapped_column(
        String(50), nullable=False, default="DRAFT", server_default=text("'DRAFT'")
    )
    stage_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    mentor_attempt_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    resume_document_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    approved_by_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    rejected_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Cooling-period bookkeeping.
    cooling_period_months: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, default=None
    )
    cooling_period_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    cooling_period_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    cooling_triggered_by: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    cooling_override_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    cooling_override_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    cooling_override_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    reminder_7d_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reminder_expiry_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class CoolingPeriodOverride(Base):
    __tablename__ = "cooling_period_overrides"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    referral_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
    )
    new_referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    candidate_pan_masked: Mapped[str] = mapped_column(String(20), nullable=False)
    original_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    overridden_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    overridden_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    override_reason: Mapped[str] = mapped_column(Text, nullable=False)


# ────────────────────────────────────────────────────────────────────
# Stage history — append-only.
# ────────────────────────────────────────────────────────────────────
class ReferralStageHistory(Base):
    __tablename__ = "referral_stage_history"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, init=False
    )
    referral_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    actor_role: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default_factory=dict, server_default=text("'{}'::jsonb")
    )


class StageDurationStat(Base):
    __tablename__ = "stage_duration_stats"

    stage: Mapped[str] = mapped_column(String(50), primary_key=True)
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    avg_hours: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    p95_hours: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


# ────────────────────────────────────────────────────────────────────
# Mentor assignments.
# ────────────────────────────────────────────────────────────────────
class MentorAssignment(Base):
    __tablename__ = "mentor_assignments"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    referral_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
    )
    mentor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    timeout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    reassigned_to: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reassigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reassigned_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reassign_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )


# ────────────────────────────────────────────────────────────────────
# AI result tables (decisions E9 + E10 + Blueprint §18).
# ────────────────────────────────────────────────────────────────────
class AiParseResult(Base):
    __tablename__ = "ai_parse_results"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    ai_touchpoint: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    azure_openai_request_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    confidence_scores: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    human_overrides: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    succeeded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    degradation_reason: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default=None
    )


class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    referral_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    risk_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    factors: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class DuplicateCheckResult(Base):
    __tablename__ = "duplicate_check_results"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    match_type: Mapped[str] = mapped_column(String(50), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    match_reasons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    matched_referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class AiAutoAction(Base):
    __tablename__ = "ai_auto_actions"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    intern_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, default=None
    )
    conditions_met: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    flags: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    hr_recommendation: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    recalled_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    recall_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


# ────────────────────────────────────────────────────────────────────
# Notifications + ConfigChangeHistory (S25-managed audit).
# ────────────────────────────────────────────────────────────────────
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    template_id: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    gmail_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED", server_default=text("'QUEUED'")
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    delivery_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    bounce_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class Task(Base):
    """Generic workflow task — substrate for AI-10 auto-routing.

    HR review, Non-Worker ID issuance, NDA signing, AD provisioning,
    badge access, certificate generation — every "human or system has
    to do something here" step lives in this table. The `task_type`
    string mirrors `shared.constants.TaskType`.
    """

    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_to: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sla_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    referral_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=True,
        default=None,
    )
    intern_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, default=None
    )
    assigned_by_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ai_routing_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    warned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    completion_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    completed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class ConfigChangeHistory(Base):
    __tablename__ = "config_change_history"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    config_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_value: Mapped[str] = mapped_column(String(50), nullable=False)
    new_value: Mapped[str] = mapped_column(String(50), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    changed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    applies_to: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="NEW_REFERRALS_ONLY",
        server_default=text("'NEW_REFERRALS_ONLY'"),
    )
    active_referrals_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    active_mentors_affected: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
