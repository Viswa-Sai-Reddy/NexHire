"""create action_tokens

Revision ID: 0004_action_tokens
Revises: 0003_sessions
Created: 2026-05-04 12:03 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_action_tokens"
down_revision: str | None = "0003_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `app.shared.constants.ActionTokenType`.
ACTION_TOKEN_TYPES = (
    "MENTOR_RESPONSE",
    "CANDIDATE_ACCESS",
    "RECALL_AUTO_ACTION",
    "EXTENSION_RESPONSE",
)


def upgrade() -> None:
    op.create_table(
        "action_tokens",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        # FK to referrals(id) is added in S1's referral migration so this
        # table can be created in S0 without a circular dependency.
        sa.Column(
            "referral_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "intern_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "used",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.dialects.postgresql.INET, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "action_type IN ('" + "','".join(ACTION_TOKEN_TYPES) + "')",
            name="ck_action_tokens_type_enum",
        ),
    )
    op.create_index(
        "idx_action_tokens_lookup", "action_tokens", ["token_hash", "used"]
    )
    op.create_index("idx_action_tokens_expiry", "action_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_action_tokens_expiry", table_name="action_tokens")
    op.drop_index("idx_action_tokens_lookup", table_name="action_tokens")
    op.drop_table("action_tokens")
