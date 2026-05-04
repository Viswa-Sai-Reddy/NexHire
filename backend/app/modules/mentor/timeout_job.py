"""APScheduler entry point for mentor-response timeouts (RULE-M2).

Runs every hour. Inside the wrapper:
  * Acquires an idempotency lock keyed on the hour bucket so a process
    restart mid-job doesn't double-fire.
  * Opens its own DB session (the scheduler runs *outside* an HTTP
    request, so there's no `get_session` dependency in scope).
  * Calls `mentor.service.handle_timeouts` which advances every PENDING
    assignment past its `timeout_at`, bumps the strike counter, and
    publishes `MentorTimedOut` events.
"""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_hourly,
    idempotent_job,
    register_interval_job,
)
from app.modules.mentor import service as mentor_service

logger = logging.getLogger("nexhire.mentor.timeout_job")


@idempotent_job("mentor_timeout", bucket=bucket_hourly, lock_ttl_seconds=3_600)
async def check_mentor_timeouts() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        handled = await mentor_service.handle_timeouts(session)
    if handled:
        logger.info("nexhire.mentor.timeouts_processed", extra={"count": handled})


def register() -> None:
    """Wire into APScheduler. Called at app startup."""
    register_interval_job(
        "mentor_timeout_hourly",
        check_mentor_timeouts,
        hours=1,
    )
