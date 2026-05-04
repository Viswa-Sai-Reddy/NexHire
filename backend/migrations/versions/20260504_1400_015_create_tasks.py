"""create tasks (Blueprint §9.1 — generic workflow task queue)

Revision ID: 0015_tasks
Revises: 0014_link_action_tokens
Created: 2026-05-04 14:00 UTC

Tasks are the substrate AI-10 (workflow auto-router) routes work onto.
HR review tasks (this slice), Non-Worker ID tasks (S3), AD provisioning
tasks (S4), badge tasks (S4), certificate tasks (S5) — all share this
table. The `task_type` enum gains values as later slices land.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_tasks"
down_revision: str | None = "0014_link_action_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `app.shared.constants.TaskType`. New values land via
# subsequent migrations (preferred) — Postgres VARCHAR + CHECK
# constraint means we ALTER the constraint, not the enum type.
TASK_TYPES = (
    "NON_WORKER_ID",
    "NDA_SIGN",
    "AD_PROVISION",
    "BADGE_ACCESS",
    "AD_DEACTIVATE",
    "BADGE_DEACTIVATE",
    "CERT_REQUEST",
    "HR_REVIEW",
    "JOINING_FORM_REVIEW",
)

TASK_STATUSES = ("PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED", "BLOCKED")


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # `referral_id` covers HR review + most pre-onboarding tasks;
        # `intern_id` is set when the task lives on the post-approval
        # `interns` row. At least one of the two should be present.
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "intern_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,  # FK to interns added in S3 once that table lands
        ),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column(
            "assigned_to",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_ai",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("ai_routing_reason", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("warned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_notes", sa.Text, nullable=True),
        sa.Column(
            "completed_by",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "task_type IN ('" + "','".join(TASK_TYPES) + "')",
            name="ck_tasks_type_enum",
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(TASK_STATUSES) + "')",
            name="ck_tasks_status_enum",
        ),
        sa.CheckConstraint(
            "referral_id IS NOT NULL OR intern_id IS NOT NULL",
            name="ck_tasks_at_least_one_anchor",
        ),
    )
    # Hot read paths for the auto-router + dashboards.
    op.create_index(
        "idx_tasks_assignee_open",
        "tasks",
        ["assigned_to", "status"],
        postgresql_where=sa.text(
            "status NOT IN ('COMPLETED', 'CANCELLED')"
        ),
    )
    op.create_index(
        "idx_tasks_referral",
        "tasks",
        ["referral_id", "task_type", "status"],
    )
    op.create_index(
        "idx_tasks_sla_open",
        "tasks",
        ["sla_deadline"],
        postgresql_where=sa.text(
            "status NOT IN ('COMPLETED', 'CANCELLED')"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_tasks_sla_open", table_name="tasks")
    op.drop_index("idx_tasks_referral", table_name="tasks")
    op.drop_index("idx_tasks_assignee_open", table_name="tasks")
    op.drop_table("tasks")
