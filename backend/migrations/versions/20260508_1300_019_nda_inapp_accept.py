"""add nda_records columns for in-app click-to-accept

Revision ID: 0019_nda_inapp
Revises: 0018_skills
Created: 2026-05-08 13:00 UTC

Replaces the OpenSign-only signing path with an in-app click-to-accept
flow for staging/pilot deployments. The candidate reads the agreement
on a NexHire page, ticks "I agree", types their full legal name, and
the server records the audit fields below into the existing
`nda_records` row. No external e-sign service required.

The OpenSign columns (`opensign_envelope_id`, `signed_document_id`,
etc.) remain in place so the OpenSign path can be re-enabled later
without a schema change.
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_nda_inapp"
down_revision: str | None = "0018_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nda_records",
        sa.Column("typed_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "nda_records",
        sa.Column(
            "accepted_ip",
            sa.dialects.postgresql.INET,
            nullable=True,
        ),
    )
    op.add_column(
        "nda_records",
        sa.Column("accepted_user_agent", sa.String(512), nullable=True),
    )
    op.add_column(
        "nda_records",
        sa.Column("text_sha256", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nda_records", "text_sha256")
    op.drop_column("nda_records", "accepted_user_agent")
    op.drop_column("nda_records", "accepted_ip")
    op.drop_column("nda_records", "typed_name")
