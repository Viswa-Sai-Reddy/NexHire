"""create documents

Revision ID: 0008_documents
Revises: 0007_colleges
Created: 2026-05-04 13:02 UTC
"""
from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_documents"
down_revision: str | None = "0007_colleges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors `app.shared.constants.DocumentType`.
DOCUMENT_TYPES = (
    "RESUME",
    "ID_PROOF",
    "EDUCATION_CERT",
    "NDA_TEMPLATE",
    "SIGNED_NDA",
    "OFFER_LETTER",
    "CERTIFICATE",
    "PHOTO",
    "PAN_CARD",
    "OTHER",
)


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("azure_blob_container", sa.String(255), nullable=False),
        sa.Column("azure_blob_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_recalled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recalled_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("retention_delete_at", sa.Date, nullable=True),
        sa.CheckConstraint(
            "document_type IN ('" + "','".join(DOCUMENT_TYPES) + "')",
            name="ck_documents_type_enum",
        ),
    )
    op.create_index("idx_documents_type", "documents", ["document_type"])
    op.create_index("idx_documents_uploaded_by", "documents", ["uploaded_by"])
    op.create_index(
        "idx_documents_retention",
        "documents",
        ["retention_delete_at"],
        postgresql_where=sa.text("retention_delete_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_documents_retention", table_name="documents")
    op.drop_index("idx_documents_uploaded_by", table_name="documents")
    op.drop_index("idx_documents_type", table_name="documents")
    op.drop_table("documents")
