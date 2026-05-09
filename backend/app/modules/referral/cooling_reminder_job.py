"""F-42 — Daily cooling-period reminder job (07:30 UTC).

Two passes:
  * 7-day-out reminder.
  * On-expiry notification.

Both write the corresponding `reminder_*_sent_at` timestamp on the
referral so the daily scheduler stays idempotent across re-runs.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_daily,
    idempotent_job,
    register_cron_job,
)
from app.middleware import audit
from app.modules.referral import cooling_period_service
from app.shared.constants import AI_SYSTEM_USER_ID

logger = logging.getLogger("nexhire.cooling.reminder_job")


@idempotent_job(
    "cooling_reminder_daily",
    bucket=bucket_daily,
    lock_ttl_seconds=24 * 3_600,
)
async def run_daily_reminders() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        ending_soon = await cooling_period_service.find_cooling_ending_in_days(
            session, days=7
        )
        now = datetime.now(UTC)
        for referral in ending_soon:
            referral.reminder_7d_sent_at = now
            await audit.publish(
                event_type="COOLING_REMINDER_7D_SENT",
                entity_type="REFERRAL",
                entity_id=referral.id,
                actor_user_id=AI_SYSTEM_USER_ID,
                actor_role="SYSTEM",
                payload={"pan_masked": referral.candidate_pan_masked},
                session=session,
            )

        expired_today = await cooling_period_service.find_cooling_expiring_today(
            session
        )
        for referral in expired_today:
            referral.reminder_expiry_sent_at = now
            await audit.publish(
                event_type="COOLING_PERIOD_NATURALLY_EXPIRED",
                entity_type="REFERRAL",
                entity_id=referral.id,
                actor_user_id=AI_SYSTEM_USER_ID,
                actor_role="SYSTEM",
                payload={"pan_masked": referral.candidate_pan_masked},
                session=session,
            )
        if ending_soon or expired_today:
            logger.info(
                "nexhire.cooling.reminder_run",
                extra={
                    "ending_soon": len(ending_soon),
                    "expired_today": len(expired_today),
                },
            )


def register() -> None:
    # Daily at 07:30 UTC (~13:00 IST).
    register_cron_job("cooling_reminder_daily", run_daily_reminders, hour="7", minute="30")
