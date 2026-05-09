"""APScheduler entry for NDA timeout (RULE-N3) + reminders (RULE-N2)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_six_hourly,
    idempotent_job,
    register_interval_job,
)
from app.modules.nda import service
from app.modules.nda.models import NdaRecord
from app.shared.constants import NdaStatus

logger = logging.getLogger("nexhire.nda.timeout_job")


@idempotent_job("nda_timeout", bucket=bucket_six_hourly, lock_ttl_seconds=6 * 3_600)
async def check_nda_timeouts() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        handled = await service.auto_reject_expired(session)
        if handled:
            logger.info("nexhire.nda.auto_rejected", extra={"count": handled})
        await _send_reminders(session)


async def _send_reminders(session) -> None:  # type: ignore[no-untyped-def]
    """Day 1, Day 2, Day 3 reminder schedule (RULE-N2).

    We mark the per-day timestamps directly on the NDA row; the
    notification module can subscribe to a future `NdaReminderDue`
    event for the actual email body. For S4 we just record the marker
    so the scheduler is idempotent — full email wiring lands when the
    reminder template is added.
    """
    now = datetime.now(UTC)
    rows = (
        await session.execute(
            select(NdaRecord).where(NdaRecord.status == NdaStatus.SENT.value)
        )
    ).scalars().all()
    for record in rows:
        if record.sent_at is None:
            continue
        elapsed = now - record.sent_at
        if elapsed >= timedelta(days=3) and record.reminder_3_sent_at is None:
            record.reminder_3_sent_at = now
        elif elapsed >= timedelta(days=2) and record.reminder_2_sent_at is None:
            record.reminder_2_sent_at = now
        elif elapsed >= timedelta(days=1) and record.reminder_1_sent_at is None:
            record.reminder_1_sent_at = now


def register() -> None:
    register_interval_job("nda_timeout_six_hourly", check_nda_timeouts, hours=6)
