"""create audit_events

Revision ID: 0001_audit_events
Revises:
Created: 2026-05-04 12:00 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_audit_events"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """audit_events — append-only, tamper-evident chain.

    See app/middleware/audit.py + Implementation_Plan.md decision B9.
    The application role gets INSERT only; UPDATE/DELETE are revoked
    at the very end of this migration so even buggy code can't mutate
    history.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.dialects.postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB,
            nullable=False,
        ),
        sa.Column("prev_checksum", sa.String(64), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False),
    )
    # Common query patterns:
    op.create_index(
        "idx_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id", "event_timestamp"],
    )
    op.create_index(
        "idx_audit_events_actor", "audit_events", ["actor_user_id", "event_timestamp"]
    )
    op.create_index(
        "idx_audit_events_event_type", "audit_events", ["event_type", "event_timestamp"]
    )

    # Immutability: the application role can only INSERT.
    # NOTE: REVOKE is conditional on the role existing. We swallow the
    # not-found case so dev environments with the default `postgres`
    # superuser don't break the migration.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexhire_app') THEN
                REVOKE UPDATE, DELETE ON audit_events FROM nexhire_app;
                GRANT INSERT, SELECT ON audit_events TO nexhire_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_audit_events_event_type", table_name="audit_events")
    op.drop_index("idx_audit_events_actor", table_name="audit_events")
    op.drop_index("idx_audit_events_entity", table_name="audit_events")
    op.drop_table("audit_events")
