"""Auth ORM models — `users`, `sessions`, `magic_links`, `action_tokens`.

Schema notes:
  * `users.role` is a Postgres enum mirroring `UserRole` in
    `shared/constants.py`. Keep them in sync (a migration alters both).
  * `users.azure_oid` is unique and nullable — candidates have no Azure
    AD identity (decision A5).
  * `users.can_mentor` is the mentor-eligibility flag (decision A4).
  * `users.out_of_office_until` supports F-29 auto-routing (decision E6).
  * `users.is_active` doubles as the terminal soft-delete marker.

Magic-link + action-token tables are owned by auth because they're the
authentication surface for non-SSO interactions (candidate access,
mentor email buttons).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default_factory=uuid4,
    )
    azure_oid: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, default=None
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stored as VARCHAR so changing the enum doesn't require migrating
    # every users row. Validation is at the boundary (Pydantic).
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    can_mentor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    out_of_office_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )


Index("idx_users_role_active", User.role, User.is_active)
Index("idx_users_can_mentor", User.can_mentor, postgresql_where=User.can_mentor)


class Session(Base):
    """Refresh-token bookkeeping. One row per active SSO session.

    The refresh token is stored bcrypt-hashed; access tokens are not
    persisted (they expire in 8h and are stateless RS256 JWTs).
    """

    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True, default=None)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default=None)


Index("idx_sessions_user_active", Session.user_id, Session.revoked_at)


class ActionToken(Base):
    """Single-use, hash-stored, time-limited tokens for email actions
    and magic links (decision E12).

    Decision B12: GET on the action URL renders a confirmation page;
    POST executes. Both share the same token; `used` flips on POST.
    """

    __tablename__ = "action_tokens"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default_factory=uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    referral_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        # FK to referrals(id) added by the S1 migration that creates the table.
        nullable=True,
        default=None,
    )
    intern_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, default=None
    )
    actor_user_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )


Index("idx_action_tokens_lookup", ActionToken.token_hash, ActionToken.used)
Index("idx_action_tokens_expiry", ActionToken.expires_at)
