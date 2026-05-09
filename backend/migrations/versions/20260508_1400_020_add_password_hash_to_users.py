"""add users.password_hash for email+password auth

Revision ID: 0020_password_hash
Revises: 0019_nda_inapp
Created: 2026-05-08 14:00 UTC

Replaces Azure AD SSO with email+password authentication. Existing rows
get an empty password_hash on upgrade — they remain login-blocked until
the seed script (or a future password-set flow) populates a real bcrypt
hash. The `azure_oid` column is kept (still nullable) so the schema
change is non-destructive; it's simply never populated again.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_password_hash"
down_revision: str | None = "0019_nda_inapp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
