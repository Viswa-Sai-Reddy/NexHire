"""add FK from action_tokens to referrals (deferred from S0)

Revision ID: 0014_link_action_tokens
Revises: 0013_notifications
Created: 2026-05-04 13:08 UTC

S0 created `action_tokens.referral_id` as a plain UUID column because
`referrals` didn't exist yet. Now that it does, attach the FK so
deletes cascade properly and orphaned tokens become impossible.
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

revision: str = "0014_link_action_tokens"
down_revision: str | None = "0013_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_action_tokens_referral",
        source_table="action_tokens",
        referent_table="referrals",
        local_cols=["referral_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_action_tokens_referral",
        "action_tokens",
        type_="foreignkey",
    )
