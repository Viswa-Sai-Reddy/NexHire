"""APScheduler wrapper for AI-5 (every 6h)."""
from __future__ import annotations

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.scheduler import (
    bucket_six_hourly,
    idempotent_job,
    register_interval_job,
)
from app.modules.ai import bottleneck


@idempotent_job(
    "bottleneck_predict",
    bucket=bucket_six_hourly,
    lock_ttl_seconds=6 * 3_600,
)
async def run_predictions() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        await bottleneck.predict_for_active_referrals(session)


def register() -> None:
    register_interval_job("bottleneck_six_hourly", run_predictions, hours=6)
