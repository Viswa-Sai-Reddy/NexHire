"""NDA records ORM."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class NdaRecord(Base):
    __tablename__ = "nda_records"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    intern_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("interns.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    opensign_envelope_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, default=None
    )
    template_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    auto_rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    signed_document_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reminder_1_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reminder_2_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reminder_3_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # In-app click-to-accept audit fields (migration 0019). Populated
    # only when the candidate accepts via the NexHire portal instead of
    # OpenSign. `text_sha256` pins the exact agreement version they
    # accepted; `typed_name` is the candidate-typed confirmation.
    typed_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    accepted_ip: Mapped[str | None] = mapped_column(
        INET, nullable=True, default=None
    )
    accepted_user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None
    )
    text_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
