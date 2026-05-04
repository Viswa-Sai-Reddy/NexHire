"""create users + seed AI_SYSTEM and first Program Owner

Revision ID: 0002_users
Revises: 0001_audit_events
Created: 2026-05-04 12:01 UTC
"""
from __future__ import annotations

import os
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_users"
down_revision: str | None = "0001_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `app.shared.constants.UserRole`. Stored as VARCHAR(32) (not a
# Postgres ENUM) so adding a new role doesn't require ALTER TYPE.
ROLE_VALUES = (
    "REFERRER",
    "MENTOR",
    "HR",
    "IT_AD",
    "ADMIN",
    "PROGRAM_OWNER",
    "CANDIDATE",
    "SYSTEM",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("azure_oid", sa.String(255), unique=True, nullable=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "can_mentor",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "out_of_office_until",
            sa.DateTime(timezone=True),
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
            "role IN ('" + "','".join(ROLE_VALUES) + "')",
            name="ck_users_role_enum",
        ),
    )
    op.create_index("idx_users_role_active", "users", ["role", "is_active"])
    op.create_index(
        "idx_users_can_mentor",
        "users",
        ["can_mentor"],
        postgresql_where=sa.text("can_mentor = true"),
    )

    # ── Seed: AI_SYSTEM (decision A2). UUID is a fixed value referenced
    # by code (`AI_SYSTEM_USER_ID` in shared/constants.py).
    op.execute(
        """
        INSERT INTO users (id, email, full_name, role, is_active)
        VALUES (
            '00000000-0000-0000-0000-000000000001',
            'ai-system@nexhire.internal',
            'NexHire AI',
            'SYSTEM',
            true
        );
        """
    )

    # ── Seed: first Program Owner (decision E20).
    # Reads `SEED_PROGRAM_OWNER_EMAIL` / `SEED_PROGRAM_OWNER_NAME` from
    # the migration environment; if unset, uses safe placeholders that
    # an admin must rotate before letting anyone else log in.
    po_email = os.environ.get("SEED_PROGRAM_OWNER_EMAIL", "program-owner@example.com")
    po_name = os.environ.get("SEED_PROGRAM_OWNER_NAME", "NexHire Program Owner")
    op.execute(
        sa.text(
            """
            INSERT INTO users (email, full_name, role, is_active)
            VALUES (:email, :name, 'PROGRAM_OWNER', true)
            ON CONFLICT (email) DO NOTHING;
            """
        ).bindparams(email=po_email, name=po_name)
    )


def downgrade() -> None:
    op.drop_index("idx_users_can_mentor", table_name="users")
    op.drop_index("idx_users_role_active", table_name="users")
    op.drop_table("users")
