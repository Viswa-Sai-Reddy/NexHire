"""Intern + JoiningForm ORM models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class Intern(Base):
    __tablename__ = "interns"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    referral_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    non_worker_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, default=None
    )
    ad_account_username: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    ad_account_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NOT_CREATED",
        server_default=text("'NOT_CREATED'"),
    )
    actual_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    actual_end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )
    extension_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    mentor_closure_feedback: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    mentor_confirmed_completion: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )


class JoiningForm(Base):
    __tablename__ = "joining_forms"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    intern_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("interns.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    personal_details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default_factory=dict, server_default=text("'{}'::jsonb")
    )
    address: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default_factory=dict, server_default=text("'{}'::jsonb")
    )
    emergency_contact: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default_factory=dict, server_default=text("'{}'::jsonb")
    )
    education_history: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    employment_history: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    govt_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default_factory=dict, server_default=text("'{}'::jsonb")
    )
    uploaded_documents: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default_factory=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default=text("'DRAFT'")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    locked_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    locked_by_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None
    )
    declaration_signed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        init=False,
    )
