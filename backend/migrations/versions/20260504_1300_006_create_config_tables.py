"""create configuration tables (cooling, mentor threshold, holidays, notif templates)

Revision ID: 0006_config_tables
Revises: 0005_outbox
Created: 2026-05-04 13:00 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_config_tables"
down_revision: str | None = "0005_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Reference data ─────────────────────────────────────────────────
COOLING_DEFAULTS = [
    ("NDA_DECLINED_REJECTED", 6, "Candidate explicitly declined NDA — 6m cooling."),
    ("TERMINATED", 6, "Candidate left mid-internship — 6m cooling."),
    ("NDA_TIMEOUT_REJECTED", 3, "Candidate did not sign NDA within deadline — 3m cooling."),
    ("HR_REJECTED", 3, "HR found candidate unfit — 3m cooling."),
    ("CANDIDATE_REJECTED", 0, "Mentor unavailability — no cooling applied (RULE-CP5)."),
    ("CLOSED", 3, "Successful completion — 3m re-join spacing."),
]

# India national holidays for the current + next 2 years.
# A subset; Program Owner can add company-specific ones via S25.
HOLIDAYS = [
    ("2026-01-26", "Republic Day", "NATIONAL"),
    ("2026-03-04", "Holi", "NATIONAL"),
    ("2026-05-01", "Labour Day", "NATIONAL"),
    ("2026-08-15", "Independence Day", "NATIONAL"),
    ("2026-10-02", "Gandhi Jayanti", "NATIONAL"),
    ("2026-11-08", "Diwali", "NATIONAL"),
    ("2026-12-25", "Christmas Day", "NATIONAL"),
    ("2027-01-26", "Republic Day", "NATIONAL"),
    ("2027-03-23", "Holi", "NATIONAL"),
    ("2027-05-01", "Labour Day", "NATIONAL"),
    ("2027-08-15", "Independence Day", "NATIONAL"),
    ("2027-10-02", "Gandhi Jayanti", "NATIONAL"),
    ("2027-10-28", "Diwali", "NATIONAL"),
    ("2027-12-25", "Christmas Day", "NATIONAL"),
]

# Notification template ids match `app.shared.constants.NotificationTemplate`.
NOTIFICATION_TEMPLATES = [
    ("NOTIF_001_REFERRAL_CONFIRMATION", "Referral submitted — confirmation"),
    ("NOTIF_002_MENTOR_ASSIGNMENT", "You've been assigned as a mentor"),
    ("NOTIF_003_NDA_ISSUANCE", "Action required: sign your NDA"),
    ("NOTIF_004_MENTOR_REJECTION_TO_REFERRER", "Mentor declined the assignment"),
    ("NOTIF_005_MENTOR_TIMEOUT_TO_REFERRER", "Mentor did not respond"),
    ("NOTIF_006_CONGRATULATIONS_TO_CANDIDATE", "Congratulations! Your internship is approved"),
    ("NOTIF_007_CERTIFICATE_DELIVERY", "Your internship certificate is ready"),
    ("NOTIF_008_CLOSURE_REMINDER", "Internship ending soon"),
    ("NOTIF_009_NDA_FINAL_WARNING", "Final reminder: sign your NDA"),
    ("NOTIF_010_OFFER_LETTER", "Your offer letter"),
    ("NOTIF_011_OFFER_LETTER_FYI_HR", "Offer letter auto-sent (HR FYI)"),
    ("NOTIF_012_CERT_AUTO_SENT_FYI", "Certificate auto-sent (HR FYI)"),
    ("NOTIF_013_COOLING_OVERRIDE_HR", "Cooling period overridden by Program Owner"),
    ("NOTIF_014_COOLING_PERIOD_APPLIED", "Cooling period applied to referral"),
    ("NOTIF_015_COOLING_ENDING_SOON", "Cooling period ending in 7 days"),
    ("NOTIF_016_COOLING_EXPIRED", "Cooling period has ended"),
    ("NOTIF_017_OFFER_LETTER_RECALLED", "Please disregard the previous offer letter"),
    ("NOTIF_018_NDA_TIMEOUT_CANDIDATE", "Your referral has been closed (NDA timeout)"),
    ("NOTIF_019_NDA_DECLINED_CANDIDATE", "Your referral has been closed (NDA declined)"),
    ("NOTIF_020_MAX_MENTOR_CANDIDATE", "Your referral could not proceed (mentor unavailability)"),
    ("NOTIF_021_HR_REJECTED_CANDIDATE", "Your application could not proceed at this time"),
]


def upgrade() -> None:
    # ────────────────────────── cooling_period_config ──
    op.create_table(
        "cooling_period_config",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("terminal_state", sa.String(50), unique=True, nullable=False),
        sa.Column("duration_months", sa.SmallInteger, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "set_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("previous_value", sa.SmallInteger, nullable=True),
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
        sa.CheckConstraint(
            "duration_months BETWEEN 0 AND 24", name="ck_cooling_duration_range"
        ),
    )
    # Seed defaults.
    for state, months, desc in COOLING_DEFAULTS:
        op.execute(
            sa.text(
                """
                INSERT INTO cooling_period_config (terminal_state, duration_months, description)
                VALUES (:state, :months, :desc)
                ON CONFLICT (terminal_state) DO NOTHING
                """
            ).bindparams(state=state, months=months, desc=desc)
        )

    # ────────────────────────── mentor_threshold_config ──
    op.create_table(
        "mentor_threshold_config",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "max_mentees",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("4"),
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "set_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "max_mentees BETWEEN 1 AND 10", name="ck_mentor_threshold_range"
        ),
    )
    op.create_index(
        "idx_mentor_threshold_current",
        "mentor_threshold_config",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )
    # Seed default 4.
    op.execute(
        """
        INSERT INTO mentor_threshold_config (max_mentees, reason, is_current)
        SELECT 4, 'Initial default — max 4 mentees per mentor', true
        WHERE NOT EXISTS (SELECT 1 FROM mentor_threshold_config WHERE is_current = true);
        """
    )

    # ────────────────────────── holidays ──
    op.create_table(
        "holidays",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False, server_default=sa.text("'NATIONAL'")),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    for date_str, name, kind in HOLIDAYS:
        op.execute(
            sa.text(
                """
                INSERT INTO holidays (date, name, type, source)
                VALUES (:d, :n, :k, 'SEED')
                ON CONFLICT (date) DO NOTHING
                """
            ).bindparams(d=date_str, n=name, k=kind)
        )

    # ────────────────────────── notification_templates ──
    op.create_table(
        "notification_templates",
        sa.Column("template_id", sa.String(100), primary_key=True),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    for tid, subj in NOTIFICATION_TEMPLATES:
        op.execute(
            sa.text(
                """
                INSERT INTO notification_templates (template_id, subject)
                VALUES (:tid, :subj)
                ON CONFLICT (template_id) DO NOTHING
                """
            ).bindparams(tid=tid, subj=subj)
        )

    # ────────────────────────── config_change_history ──
    # Append-only log used by S25 (Program Owner config panel).
    op.create_table(
        "config_change_history",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("config_type", sa.String(50), nullable=False),
        sa.Column("config_key", sa.String(100), nullable=False),
        sa.Column("previous_value", sa.String(50), nullable=False),
        sa.Column("new_value", sa.String(50), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "changed_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "applies_to",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'NEW_REFERRALS_ONLY'"),
        ),
        sa.Column("active_referrals_count", sa.Integer, nullable=True),
        sa.Column("active_mentors_affected", sa.Integer, nullable=True),
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexhire_app') THEN
                REVOKE UPDATE, DELETE ON config_change_history FROM nexhire_app;
                GRANT INSERT, SELECT ON config_change_history TO nexhire_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("config_change_history")
    op.drop_table("notification_templates")
    op.drop_table("holidays")
    op.drop_index("idx_mentor_threshold_current", table_name="mentor_threshold_config")
    op.drop_table("mentor_threshold_config")
    op.drop_table("cooling_period_config")
