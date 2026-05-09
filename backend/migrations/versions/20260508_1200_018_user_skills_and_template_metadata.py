"""add users.skills and notification_templates editor columns

Revision ID: 0018_skills
Revises: 0017_nda
Created: 2026-05-08 12:00 UTC

Adds:
  * users.skills (JSONB, default []) — feeds AI-2 mentor skill matching
    (Implementation_Plan §17.7 / Functionality_Matrix #7).
  * notification_templates.updated_by, updated_at — so the admin template
    management endpoints (#13) can record who last edited each template.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_skills"
down_revision: str | None = "0017_nda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "skills",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(
        "idx_users_skills_gin",
        "users",
        ["skills"],
        postgresql_using="gin",
    )

    op.add_column(
        "notification_templates",
        sa.Column(
            "updated_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "notification_templates",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_templates", "updated_at")
    op.drop_column("notification_templates", "updated_by")
    op.drop_index("idx_users_skills_gin", table_name="users")
    op.drop_column("users", "skills")
