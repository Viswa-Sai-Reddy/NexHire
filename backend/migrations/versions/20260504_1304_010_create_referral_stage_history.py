"""create referral_stage_history (decision E2)

Revision ID: 0010_stage_history
Revises: 0009_referrals
Created: 2026-05-04 13:04 UTC

Append-only FSM transition log. The state machine writes one row per
transition; analytics + bottleneck prediction read from this table.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_stage_history"
down_revision: str | None = "0009_referrals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referral_stage_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referrals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "actor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "idx_stage_history_referral",
        "referral_stage_history",
        ["referral_id", "entered_at"],
    )
    op.create_index(
        "idx_stage_history_to_status_time",
        "referral_stage_history",
        ["to_status", "entered_at"],
    )

    # Append-only enforcement at DB level.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexhire_app') THEN
                REVOKE UPDATE, DELETE ON referral_stage_history FROM nexhire_app;
                GRANT INSERT, SELECT ON referral_stage_history TO nexhire_app;
            END IF;
        END
        $$;
        """
    )

    # Companion analytics table: rolling per-stage averages used by AI-5
    # (decision E4). Updated nightly by S6's stats job.
    op.create_table(
        "stage_duration_stats",
        sa.Column("stage", sa.String(50), primary_key=True),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("avg_hours", sa.Float, nullable=True),
        sa.Column("p95_hours", sa.Float, nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("stage_duration_stats")
    op.drop_index("idx_stage_history_to_status_time", table_name="referral_stage_history")
    op.drop_index("idx_stage_history_referral", table_name="referral_stage_history")
    op.drop_table("referral_stage_history")
