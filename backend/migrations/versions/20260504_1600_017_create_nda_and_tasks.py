"""create nda_records + extend tasks/documents for S4 access flows

Revision ID: 0017_nda
Revises: 0016_interns
Created: 2026-05-04 16:00 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_nda"
down_revision: str | None = "0016_interns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NDA_STATUSES = ("PENDING", "SENT", "SIGNED", "DECLINED", "EXPIRED")


def upgrade() -> None:
    op.create_table(
        "nda_records",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "intern_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("interns.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("opensign_envelope_id", sa.String(255), unique=True, nullable=True),
        sa.Column("template_version", sa.String(50), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "signed_document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reminder_1_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_2_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_3_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('" + "','".join(NDA_STATUSES) + "')",
            name="ck_nda_records_status_enum",
        ),
    )
    op.create_index(
        "idx_nda_pending_timeout",
        "nda_records",
        ["status", "sent_at"],
        postgresql_where=sa.text("status IN ('SENT','PENDING')"),
    )

    # Extend `tasks.intern_id` with the deferred FK now that interns
    # exists. (S2's migration left it as a plain UUID.)
    op.create_foreign_key(
        "fk_tasks_intern",
        source_table="tasks",
        referent_table="interns",
        local_cols=["intern_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # ai_auto_actions.intern_id FK too (S2's migration left it open).
    op.create_foreign_key(
        "fk_ai_auto_actions_intern",
        source_table="ai_auto_actions",
        referent_table="interns",
        local_cols=["intern_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_auto_actions_intern", "ai_auto_actions", type_="foreignkey")
    op.drop_constraint("fk_tasks_intern", "tasks", type_="foreignkey")
    op.drop_index("idx_nda_pending_timeout", table_name="nda_records")
    op.drop_table("nda_records")
