"""create referrals (the core entity)

Revision ID: 0009_referrals
Revises: 0008_documents
Created: 2026-05-04 13:03 UTC

Includes:
  * PAN columns (decision A3): hash for lookup, encrypted blob for display.
  * Cooling-period bookkeeping columns (Blueprint §19.3).
  * Stage-tracking columns (decision E2).
  * Reminder timestamps (decision E1).
  * Auto-approval audit columns.
  * The locked unique index on `candidate_pan_hash` for active referrals
    (drives F-33 hard-block).
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_referrals"
down_revision: str | None = "0008_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `ReferralStatus` (Implementation_Plan A6).
REFERRAL_STATUSES = (
    "DRAFT",
    "SUBMITTED",
    "MENTOR_PENDING",
    "MENTOR_ACCEPTED",
    "MENTOR_REJECTED",
    "MENTOR_TIMED_OUT",
    "HR_REVIEW",
    "CORRECTION_NEEDED",
    "APPROVED",
    "JOINING_FORM_PENDING",
    "JOINING_FORM_SUBMITTED",
    "JOINING_FORM_LOCKED",
    "ID_PENDING",
    "ID_ISSUED",
    "NDA_PENDING",
    "NDA_SIGNED",
    "ACCESS_PENDING",
    "ACTIVE",
    "EXTENDED",
    "CLOSURE_PENDING",
    "CLOSED",
    "HR_REJECTED",
    "CANDIDATE_REJECTED",
    "NDA_TIMEOUT_REJECTED",
    "NDA_DECLINED_REJECTED",
    "TERMINATED",
)

# Statuses that block a new referral via PAN active-duplicate check.
ACTIVE_STATUSES = tuple(
    s
    for s in REFERRAL_STATUSES
    if s
    not in (
        "CLOSED",
        "HR_REJECTED",
        "CANDIDATE_REJECTED",
        "NDA_TIMEOUT_REJECTED",
        "NDA_DECLINED_REJECTED",
        "TERMINATED",
    )
)


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referrer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "mentor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        # ── Candidate snapshot (denormalized for audit + speed) ──
        sa.Column("candidate_name", sa.String(255), nullable=False),
        sa.Column("candidate_email", sa.String(255), nullable=False),
        sa.Column("candidate_phone", sa.String(20), nullable=True),
        sa.Column(
            "college_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("colleges.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("candidate_year_of_study", sa.SmallInteger, nullable=False),
        sa.Column("candidate_graduation_year", sa.SmallInteger, nullable=False),
        # ── PAN (decision A3) ──
        # `_hash`: HMAC-SHA256 with peppered key — used by all dedup
        # queries + the unique index.
        # `_encrypted`: AES-256-GCM ciphertext, used only when HR clicks
        # "Reveal PAN".
        # `_masked`: cached display form ("ABCDE****F").
        sa.Column("candidate_pan_hash", sa.String(64), nullable=False),
        sa.Column("candidate_pan_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("candidate_pan_masked", sa.String(20), nullable=False),
        # ── Internship details ──
        sa.Column("project_title", sa.String(255), nullable=True),
        sa.Column("project_overview", sa.Text, nullable=True),
        sa.Column("joining_location", sa.String(255), nullable=True),
        sa.Column("internship_start_date", sa.Date, nullable=True),
        sa.Column("internship_end_date", sa.Date, nullable=True),
        sa.Column("relationship_declaration", sa.String(50), nullable=True),
        sa.Column("relationship_declaration_detail", sa.Text, nullable=True),
        sa.Column(
            "unpaid_consent",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "inperson_ready",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # ── Status & FSM bookkeeping ──
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "current_stage",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "stage_entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "mentor_attempt_count",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "resume_document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_by_label", sa.String(50), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rejected_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        # ── Cooling period (Blueprint §19.3) ──
        sa.Column("cooling_period_months", sa.SmallInteger, nullable=True),
        sa.Column("cooling_period_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooling_period_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooling_triggered_by", sa.String(50), nullable=True),
        sa.Column("cooling_override_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cooling_override_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cooling_override_reason", sa.Text, nullable=True),
        # ── Reminder timestamps (decision E1) ──
        sa.Column("reminder_7d_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_expiry_sent_at", sa.DateTime(timezone=True), nullable=True),
        # ── Standard timestamps ──
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # ── Constraints ──
        sa.CheckConstraint(
            "status IN ('" + "','".join(REFERRAL_STATUSES) + "')",
            name="ck_referrals_status_enum",
        ),
        sa.CheckConstraint(
            "candidate_year_of_study BETWEEN 2 AND 4", name="ck_referrals_year_range"
        ),
        sa.CheckConstraint(
            "mentor_attempt_count BETWEEN 0 AND 3",
            name="ck_referrals_mentor_attempt_range",
        ),
        sa.CheckConstraint(
            "(internship_start_date IS NULL OR internship_end_date IS NULL OR "
            "internship_end_date - internship_start_date BETWEEN 28 AND 182)",
            name="ck_referrals_duration_range",
        ),
        sa.CheckConstraint(
            "referrer_id <> mentor_id OR mentor_id IS NULL",
            name="ck_referrals_referrer_neq_mentor",
        ),
    )

    # ── Indexes ──
    op.create_index("idx_referrals_referrer", "referrals", ["referrer_id", "status"])
    op.create_index("idx_referrals_mentor", "referrals", ["mentor_id", "status"])
    op.create_index("idx_referrals_status", "referrals", ["status"])
    op.create_index(
        "idx_referrals_stage_entered",
        "referrals",
        ["current_stage", "stage_entered_at"],
    )
    op.create_index(
        "idx_referrals_pan_cooling",
        "referrals",
        ["candidate_pan_hash", "cooling_period_end_at"],
        postgresql_where=sa.text("cooling_period_end_at IS NOT NULL"),
    )

    # F-33 hard-block index: at most one *active* referral per PAN.
    # Active = any non-terminal status.
    active_predicate = "status IN ('" + "','".join(ACTIVE_STATUSES) + "')"
    op.execute(
        f"""
        CREATE UNIQUE INDEX idx_referrals_active_pan
            ON referrals (candidate_pan_hash)
            WHERE {active_predicate};
        """
    )

    # ── College-cap view (RULE-E2 driver) ──
    op.execute(
        f"""
        CREATE VIEW referrer_college_counts AS
            SELECT referrer_id, college_id, COUNT(*) AS active_count
            FROM referrals
            WHERE {active_predicate}
            GROUP BY referrer_id, college_id;
        """
    )

    # ── Cooling-period overrides audit (Blueprint §19.3) ──
    op.create_table(
        "cooling_period_overrides",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "new_referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("candidate_pan_masked", sa.String(20), nullable=False),
        sa.Column("original_end_date", sa.Date, nullable=False),
        sa.Column(
            "overridden_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "overridden_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("override_reason", sa.Text, nullable=False),
        sa.CheckConstraint(
            "char_length(override_reason) >= 50",
            name="ck_cooling_override_reason_min_length",
        ),
    )


def downgrade() -> None:
    op.drop_table("cooling_period_overrides")
    op.execute("DROP VIEW IF EXISTS referrer_college_counts;")
    op.drop_index("idx_referrals_active_pan", table_name="referrals")
    op.drop_index("idx_referrals_pan_cooling", table_name="referrals")
    op.drop_index("idx_referrals_stage_entered", table_name="referrals")
    op.drop_index("idx_referrals_status", table_name="referrals")
    op.drop_index("idx_referrals_mentor", table_name="referrals")
    op.drop_index("idx_referrals_referrer", table_name="referrals")
    op.drop_table("referrals")
