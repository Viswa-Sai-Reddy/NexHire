"""create interns + joining_forms + link action_tokens.intern_id

Revision ID: 0016_interns
Revises: 0015_tasks
Created: 2026-05-04 15:00 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_interns"
down_revision: str | None = "0015_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INTERN_STATUSES = (
    "PENDING",
    "ACCESS_PENDING",
    "ACTIVE",
    "EXTENDED",
    "CLOSURE_PENDING",
    "CLOSED",
    "TERMINATED",
)
AD_STATUSES = (
    "NOT_CREATED",
    "PROVISIONING",
    "PROVISIONED",
    "ACTIVE",
    "DISABLED",
)
JOINING_FORM_STATUSES = ("DRAFT", "SUBMITTED", "LOCKED")


def upgrade() -> None:
    # ── interns ──────────────────────────────────────────────────
    op.create_table(
        "interns",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="RESTRICT"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("non_worker_id", sa.String(100), unique=True, nullable=True),
        sa.Column(
            "ad_account_username", sa.String(255), nullable=True
        ),
        sa.Column(
            "ad_account_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'NOT_CREATED'"),
        ),
        sa.Column("actual_start_date", sa.Date, nullable=True),
        sa.Column("actual_end_date", sa.Date, nullable=True),
        sa.Column(
            "extension_count",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "mentor_closure_feedback",
            sa.dialects.postgresql.JSONB,
            nullable=True,
        ),
        sa.Column("mentor_confirmed_completion", sa.Boolean, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
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
            "status IN ('" + "','".join(INTERN_STATUSES) + "')",
            name="ck_interns_status_enum",
        ),
        sa.CheckConstraint(
            "ad_account_status IN ('" + "','".join(AD_STATUSES) + "')",
            name="ck_interns_ad_status_enum",
        ),
        sa.CheckConstraint(
            "extension_count BETWEEN 0 AND 2",
            name="ck_interns_extension_range",
        ),
    )
    op.create_index("idx_interns_user", "interns", ["user_id"])
    op.create_index("idx_interns_status", "interns", ["status"])

    # ── joining_forms ────────────────────────────────────────────
    op.create_table(
        "joining_forms",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "intern_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interns.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "personal_details",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "address",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "emergency_contact",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "education_history",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "employment_history",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "govt_ids",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "uploaded_documents",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column(
            "version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "locked_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("locked_by_label", sa.String(50), nullable=True),
        sa.Column(
            "declaration_signed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(JOINING_FORM_STATUSES) + "')",
            name="ck_joining_forms_status_enum",
        ),
    )
    op.create_index("idx_joining_forms_status", "joining_forms", ["status"])

    # ── action_tokens.intern_id FK (deferred from S0) ────────────
    op.create_foreign_key(
        "fk_action_tokens_intern",
        source_table="action_tokens",
        referent_table="interns",
        local_cols=["intern_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_action_tokens_intern", "action_tokens", type_="foreignkey"
    )
    op.drop_index("idx_joining_forms_status", table_name="joining_forms")
    op.drop_table("joining_forms")
    op.drop_index("idx_interns_status", table_name="interns")
    op.drop_index("idx_interns_user", table_name="interns")
    op.drop_table("interns")
