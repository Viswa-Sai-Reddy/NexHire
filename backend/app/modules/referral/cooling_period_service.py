"""Cooling-period service — Blueprint §19 + Implementation_Plan A11.

Three operations:
  * `get_status(pan_hash)` — what cooling state is this candidate in?
    Used at the head of the PAN check decision tree (F-40 step 2).
  * `apply(referral_id, terminal_state, session)` — write the cooling
    columns on the referral that just transitioned to a terminal state.
    Reads `cooling_period_config` for duration, so live config changes
    apply only to NEW terminal-state events (decision §20.5).
  * `apply_override(...)` — Program Owner override (RULE-CP7).

Cooling state is stored *on the most recent terminal referral for the
PAN*. New referrals never inherit cooling — they're blocked until the
cooling on the previous referral elapses.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.referral.models import (
    CoolingPeriodConfig,
    CoolingPeriodOverride,
    Referral,
)
from app.shared.constants import (
    COOLING_OVERRIDE_MIN_REASON_LENGTH,
    UserRole,
)
from app.shared.exceptions import (
    InsufficientPermissionsError,
    InvalidTerminalStateError,
    OverrideReasonTooShortError,
)

logger = logging.getLogger("nexhire.cooling")


@dataclass(frozen=True, slots=True)
class CoolingStatus:
    """Result of a PAN-scoped cooling check."""

    is_in_cooling: bool
    terminal_state: str | None = None
    cooling_start: date | None = None
    cooling_end: date | None = None
    days_remaining: int | None = None
    months_duration: int | None = None
    override_applied: bool = False
    referral_id: UUID | None = None


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def get_status(session: AsyncSession, *, pan_hash: str) -> CoolingStatus:
    """Resolve the cooling state for a PAN.

    Looks at the most recent referral whose `cooling_period_end_at` is
    set (i.e. it reached a cooling-bearing terminal state). Returns
    `is_in_cooling=False` for: no prior referral, 0-month entries
    (CANDIDATE_REJECTED), naturally elapsed periods, or PO overrides.
    """
    result = (
        await session.execute(
            select(Referral)
            .where(
                Referral.candidate_pan_hash == pan_hash,
                Referral.cooling_period_end_at.is_not(None),
            )
            .order_by(Referral.cooling_period_start_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if result is None:
        return CoolingStatus(is_in_cooling=False)

    if result.cooling_period_months in (None, 0):
        # CANDIDATE_REJECTED is recorded for history but never blocks.
        return CoolingStatus(
            is_in_cooling=False,
            terminal_state=result.cooling_triggered_by,
            referral_id=result.id,
        )

    if result.cooling_override_at is not None:
        return CoolingStatus(
            is_in_cooling=False,
            override_applied=True,
            terminal_state=result.cooling_triggered_by,
            referral_id=result.id,
        )

    today = date.today()
    end_date = result.cooling_period_end_at.date() if result.cooling_period_end_at else today
    if today >= end_date:
        return CoolingStatus(
            is_in_cooling=False,
            terminal_state=result.cooling_triggered_by,
            referral_id=result.id,
        )

    return CoolingStatus(
        is_in_cooling=True,
        terminal_state=result.cooling_triggered_by,
        cooling_start=result.cooling_period_start_at.date()
        if result.cooling_period_start_at
        else None,
        cooling_end=end_date,
        days_remaining=(end_date - today).days,
        months_duration=result.cooling_period_months,
        referral_id=result.id,
    )


async def apply(
    session: AsyncSession,
    *,
    referral_id: UUID,
    terminal_state: str,
) -> None:
    """Record cooling on a referral that just reached a terminal state.

    Reads `cooling_period_config.duration_months` at call time so the
    *current* policy applies. Existing rows are never recomputed
    (decision §20.5).
    """
    config = (
        await session.execute(
            select(CoolingPeriodConfig).where(
                CoolingPeriodConfig.terminal_state == terminal_state,
                CoolingPeriodConfig.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if config is None:
        # Unknown terminal state — log warning, no cooling applied.
        # (Different from CANDIDATE_REJECTED which has duration=0.)
        logger.warning(
            "nexhire.cooling.config_not_found",
            extra={"terminal_state": terminal_state},
        )
        return

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one()

    duration_months = config.duration_months
    start = _utcnow()
    end = start + relativedelta(months=duration_months) if duration_months > 0 else start

    referral.cooling_period_months = duration_months
    referral.cooling_period_start_at = start
    referral.cooling_period_end_at = end
    referral.cooling_triggered_by = terminal_state
    referral.updated_at = start

    await audit.publish(
        event_type="COOLING_PERIOD_APPLIED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_role="SYSTEM",
        payload={
            "terminal_state": terminal_state,
            "duration_months": duration_months,
            "cooling_start": start.isoformat(),
            "cooling_end": end.isoformat(),
            "pan_masked": referral.candidate_pan_masked,
        },
        session=session,
    )


async def apply_override(
    session: AsyncSession,
    *,
    referral_id: UUID,
    program_owner_id: UUID,
    program_owner_role: UserRole,
    reason: str,
) -> None:
    """Program Owner override (RULE-CP7).

    Guards: actor must be PROGRAM_OWNER; reason ≥ 50 chars.
    Effects: cooling end set to NOW(); override audit row inserted;
    immutable audit event published.
    """
    if program_owner_role is not UserRole.PROGRAM_OWNER:
        raise InsufficientPermissionsError()
    if len(reason.strip()) < COOLING_OVERRIDE_MIN_REASON_LENGTH:
        raise OverrideReasonTooShortError()

    referral = (
        await session.execute(select(Referral).where(Referral.id == referral_id))
    ).scalar_one_or_none()
    if referral is None:
        raise InvalidTerminalStateError(
            user_message="Referral not found for cooling override."
        )

    now = _utcnow()
    original_end = referral.cooling_period_end_at
    if original_end is None:
        # Nothing to override.
        raise InvalidTerminalStateError(
            user_message="This referral has no active cooling period to override."
        )

    referral.cooling_period_end_at = now
    referral.cooling_override_at = now
    referral.cooling_override_by = program_owner_id
    referral.cooling_override_reason = reason
    referral.updated_at = now

    session.add(
        CoolingPeriodOverride(
            referral_id=referral.id,
            candidate_pan_masked=referral.candidate_pan_masked,
            original_end_date=original_end.date(),
            overridden_by=program_owner_id,
            override_reason=reason,
        )
    )

    await audit.publish(
        event_type="COOLING_PERIOD_OVERRIDDEN",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=program_owner_id,
        actor_role="PROGRAM_OWNER",
        payload={
            "original_cooling_end": original_end.isoformat(),
            "override_reason": reason,
            "pan_masked": referral.candidate_pan_masked,
            "overridden_at": now.isoformat(),
        },
        session=session,
    )


# ────────────────────────────────────────────────────────────────────
# Reminder helpers used by the daily APScheduler job (F-42).
# ────────────────────────────────────────────────────────────────────
async def find_cooling_ending_in_days(
    session: AsyncSession, *, days: int
) -> list[Referral]:
    target = date.today() + timedelta(days=days)
    return list(
        (
            await session.execute(
                text(
                    """
                    SELECT *
                    FROM referrals
                    WHERE cooling_period_end_at::date = :target
                    AND cooling_period_months > 0
                    AND cooling_override_at IS NULL
                    AND reminder_7d_sent_at IS NULL
                    """
                ).bindparams(target=target)
            )
        )
        .scalars()
        .all()
    )


async def find_cooling_expiring_today(session: AsyncSession) -> list[Referral]:
    today = date.today()
    return list(
        (
            await session.execute(
                text(
                    """
                    SELECT *
                    FROM referrals
                    WHERE cooling_period_end_at::date = :today
                    AND cooling_period_months > 0
                    AND cooling_override_at IS NULL
                    AND reminder_expiry_sent_at IS NULL
                    """
                ).bindparams(today=today)
            )
        )
        .scalars()
        .all()
    )
