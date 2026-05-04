"""create notifications

Revision ID: 0013_notifications
Revises: 0012_ai_tables
Created: 2026-05-04 13:07 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_notifications"
down_revision: str | None = "0012_ai_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NOTIFICATION_STATUSES = ("QUEUED", "SENDING", "SENT", "BOUNCED", "FAILED")


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("template_id", sa.String(100), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        # Body itself is NOT stored — only its hash. Audit + ops never see PII.
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("gmail_message_id", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String(50), nullable=True),
        sa.Column("bounce_reason", sa.Text, nullable=True),
        sa.Column(
            "retry_count",
            sa.SmallInteger,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('" + "','".join(NOTIFICATION_STATUSES) + "')",
            name="ck_notifications_status_enum",
        ),
    )
    op.create_index(
        "idx_notifications_referral",
        "notifications",
        ["referral_id", "queued_at"],
    )
    op.create_index(
        "idx_notifications_status_queued",
        "notifications",
        ["status", "queued_at"],
        postgresql_where=sa.text("status IN ('QUEUED', 'FAILED')"),
    )
    op.create_index(
        "idx_notifications_recipient",
        "notifications",
        ["recipient_email", "queued_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_notifications_recipient", table_name="notifications")
    op.drop_index("idx_notifications_status_queued", table_name="notifications")
    op.drop_index("idx_notifications_referral", table_name="notifications")
    op.drop_table("notifications")
