"""Program-Owner config service (Blueprint §20).

Two settings PO can change at runtime:
  * Mentor capacity threshold (1–10).
  * Per-state cooling-period duration (0–24 months;
    CANDIDATE_REJECTED locked at 0).

Every change writes the canonical config row + an immutable
`config_change_history` row; an audit event is published. New
referrals/terminal events read the *current* row at decision time, so
active records are never retroactively affected.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.referral.models import (
    ConfigChangeHistory,
    CoolingPeriodConfig,
    MentorThresholdConfig,
)
from app.shared.constants import ReferralStatus, UserRole
from app.shared.exceptions import (
    CannotPenalizeCandidateRejectedError,
    ConfigValueUnchangedError,
    InsufficientPermissionsError,
    InvalidCoolingDurationError,
    InvalidMentorThresholdError,
    InvalidTerminalStateError,
)

logger = logging.getLogger("nexhire.admin.config_service")


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ────────────────────────────────────────────────────────────────────
# Mentor threshold.
# ────────────────────────────────────────────────────────────────────
async def get_mentor_threshold(session: AsyncSession) -> int:
    row = (
        await session.execute(
            select(MentorThresholdConfig).where(
                MentorThresholdConfig.is_current.is_(True)
            )
        )
    ).scalar_one()
    return row.max_mentees


async def set_mentor_threshold(
    session: AsyncSession,
    *,
    new_value: int,
    actor_user_id: UUID,
    actor_role: UserRole,
    reason: str | None = None,
) -> int:
    if actor_role is not UserRole.PROGRAM_OWNER:
        raise InsufficientPermissionsError()
    if not (1 <= new_value <= 10):
        raise InvalidMentorThresholdError()

    current_row = (
        await session.execute(
            select(MentorThresholdConfig).where(
                MentorThresholdConfig.is_current.is_(True)
            )
        )
    ).scalar_one()
    if current_row.max_mentees == new_value:
        raise ConfigValueUnchangedError(
            user_message=f"Mentor threshold is already {new_value}."
        )

    previous = current_row.max_mentees
    current_row.is_current = False

    new_row = MentorThresholdConfig(
        max_mentees=new_value,
        set_by=actor_user_id,
        reason=reason,
        is_current=True,
    )
    session.add(new_row)

    session.add(
        ConfigChangeHistory(
            config_type="MENTOR_THRESHOLD",
            config_key="max_mentees",
            previous_value=str(previous),
            new_value=str(new_value),
            unit="mentees",
            reason=reason,
            changed_by=actor_user_id,
        )
    )
    await audit.publish(
        event_type="MENTOR_THRESHOLD_CHANGED",
        entity_type="CONFIG",
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={"previous": previous, "new": new_value, "reason": reason},
        session=session,
    )
    return new_value


# ────────────────────────────────────────────────────────────────────
# Cooling-period duration.
# ────────────────────────────────────────────────────────────────────
async def list_cooling_periods(session: AsyncSession) -> list[CoolingPeriodConfig]:
    rows = (
        await session.execute(
            select(CoolingPeriodConfig).order_by(CoolingPeriodConfig.terminal_state)
        )
    ).scalars().all()
    return list(rows)


async def set_cooling_period(
    session: AsyncSession,
    *,
    terminal_state: str,
    new_duration_months: int,
    actor_user_id: UUID,
    actor_role: UserRole,
    reason: str | None = None,
) -> int:
    if actor_role is not UserRole.PROGRAM_OWNER:
        raise InsufficientPermissionsError()
    if not (0 <= new_duration_months <= 24):
        raise InvalidCoolingDurationError()
    if (
        terminal_state == ReferralStatus.CANDIDATE_REJECTED.value
        and new_duration_months > 0
    ):
        raise CannotPenalizeCandidateRejectedError()

    row = (
        await session.execute(
            select(CoolingPeriodConfig).where(
                CoolingPeriodConfig.terminal_state == terminal_state
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise InvalidTerminalStateError(
            user_message=f"Unknown terminal state: {terminal_state}"
        )
    if row.duration_months == new_duration_months:
        raise ConfigValueUnchangedError(
            user_message=(
                f"Cooling period for {terminal_state} is already "
                f"{new_duration_months} months."
            )
        )

    previous = row.duration_months
    row.previous_value = previous
    row.duration_months = new_duration_months
    row.effective_from = _utcnow()
    row.set_by = actor_user_id
    row.reason = reason
    row.updated_at = _utcnow()

    session.add(
        ConfigChangeHistory(
            config_type="COOLING_PERIOD",
            config_key=terminal_state,
            previous_value=str(previous),
            new_value=str(new_duration_months),
            unit="months",
            reason=reason,
            changed_by=actor_user_id,
            applies_to="NEW_TERMINAL_STATES_ONLY",
        )
    )
    await audit.publish(
        event_type="COOLING_PERIOD_CONFIG_CHANGED",
        entity_type="CONFIG",
        actor_user_id=actor_user_id,
        actor_role=actor_role.value,
        payload={
            "terminal_state": terminal_state,
            "previous_duration_months": previous,
            "new_duration_months": new_duration_months,
            "reason": reason,
        },
        session=session,
    )
    return new_duration_months


# ────────────────────────────────────────────────────────────────────
# History (read-only).
# ────────────────────────────────────────────────────────────────────
async def list_history(
    session: AsyncSession, *, limit: int = 100
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, config_type, config_key, previous_value, new_value,
                       unit, reason, changed_by, changed_at, applies_to
                FROM config_change_history
                ORDER BY changed_at DESC
                LIMIT :limit
                """
            ).bindparams(limit=limit)
        )
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "get_mentor_threshold",
    "list_cooling_periods",
    "list_history",
    "set_cooling_period",
    "set_mentor_threshold",
]


# Suppress unused-import warning when loaded standalone.
_ = cast
