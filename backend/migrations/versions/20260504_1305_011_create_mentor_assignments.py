"""create mentor_assignments

Revision ID: 0011_mentor_assignments
Revises: 0010_stage_history
Created: 2026-05-04 13:05 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_mentor_assignments"
down_revision: str | None = "0010_stage_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `MentorAssignmentStatus`.
ASSIGNMENT_STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "TIMED_OUT", "REASSIGNED")


def upgrade() -> None:
    op.create_table(
        "mentor_assignments",
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
            "mentor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.SmallInteger, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        # Decision A14: HR mid-flow reassignment. When `status =
        # REASSIGNED`, points to the mentor that took over.
        sa.Column(
            "reassigned_to",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reassigned_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reassign_reason", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('" + "','".join(ASSIGNMENT_STATUSES) + "')",
            name="ck_mentor_assignment_status_enum",
        ),
        sa.CheckConstraint(
            "attempt_number BETWEEN 1 AND 3",
            name="ck_mentor_assignment_attempt_range",
        ),
    )
    op.create_index(
        "idx_mentor_assignments_referral",
        "mentor_assignments",
        ["referral_id", "attempt_number"],
        unique=True,
    )
    op.create_index(
        "idx_mentor_assignments_pending_timeout",
        "mentor_assignments",
        ["status", "timeout_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "idx_mentor_assignments_mentor_status",
        "mentor_assignments",
        ["mentor_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_mentor_assignments_mentor_status", table_name="mentor_assignments"
    )
    op.drop_index(
        "idx_mentor_assignments_pending_timeout", table_name="mentor_assignments"
    )
    op.drop_index("idx_mentor_assignments_referral", table_name="mentor_assignments")
    op.drop_table("mentor_assignments")
