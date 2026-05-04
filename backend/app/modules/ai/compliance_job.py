"""APScheduler wrapper for AI-7 compliance checks (every 6h)."""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_six_hourly,
    idempotent_job,
    register_interval_job,
)
from app.modules.ai import compliance_check

logger = logging.getLogger("nexhire.ai.compliance_job")


@idempotent_job(
    "compliance_check",
    bucket=bucket_six_hourly,
    lock_ttl_seconds=6 * 3_600,
)
async def run_compliance_check() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        results = await compliance_check.run_for_due_interns(session)
    if results:
        logger.info(
            "nexhire.ai.compliance_check_run",
            extra={"intern_count": len(results)},
        )


def register() -> None:
    register_interval_job("compliance_check_six_hourly", run_compliance_check, hours=6)
