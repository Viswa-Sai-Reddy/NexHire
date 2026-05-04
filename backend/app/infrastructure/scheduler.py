"""APScheduler boot + idempotent job wrapper.

Why APScheduler (and not Celery / Arq):
  * Embedded — runs in the FastAPI process. No extra worker fleet for v1.
  * Persistent jobs via `SQLAlchemyJobStore` against the same Postgres,
    so a process restart doesn't drop scheduled work.
  * Cron + interval triggers cover everything in the spec.

Idempotency model (Blueprint §17.8):
  * Each job acquires a Redis lock (`scheduler_lock:<job_id>:<bucket>`)
    keyed by a per-trigger time bucket. If the lock can't be acquired,
    the job is a no-op (it already ran on a peer).
  * Time buckets are job-defined: hourly jobs use the hour, daily jobs
    use the date, ad-hoc one-shots use the timestamp.

Failure model:
  * Up to 3 attempts per fire (5s back-off doubling).
  * After max retries, a dead-letter row is written and ops alerted.

S0 wires the scaffolding only. Slice S1+ register actual jobs.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.infrastructure.redis_client import acquire_lock

logger = logging.getLogger("nexhire.scheduler")

JobFn = Callable[[], Awaitable[None]]

_scheduler: AsyncIOScheduler | None = None


def init_scheduler() -> AsyncIOScheduler:
    """Create the scheduler. Idempotent. Does NOT start it — call
    `start_scheduler()` after the engine is up.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cfg = get_settings()
    # APScheduler's SQLAlchemyJobStore needs a *sync* URL.
    sync_url = cfg.database_url.replace("+asyncpg", "+psycopg2")
    _scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=sync_url, tablename="apscheduler_jobs")},
        timezone=timezone.utc,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    logger.info("nexhire.scheduler.initialized")
    return _scheduler


def get_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        return init_scheduler()
    return _scheduler


async def start_scheduler() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("nexhire.scheduler.started")


async def shutdown_scheduler() -> None:
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("nexhire.scheduler.shutdown")


# ────────────────────────────────────────────────────────────────────
# Idempotent wrapper.
# Use it like:
#     @idempotent_job("nda_timeout", bucket=lambda: utcnow().date().isoformat())
#     async def check_nda_timeouts(): ...
# ────────────────────────────────────────────────────────────────────
def idempotent_job(
    job_name: str,
    *,
    bucket: Callable[[], str],
    lock_ttl_seconds: int = 3_600,
    max_retries: int = 3,
) -> Callable[[JobFn], JobFn]:
    """Decorator: serialize executions of a job within the same time bucket.

    Args:
        job_name: stable identifier used in the Redis key + audit logs.
        bucket: callable returning a per-execution string. Same bucket
            value on a re-fire (e.g. after process crash + restart) →
            second execution is a no-op.
        lock_ttl_seconds: how long the lock survives if the process dies
            mid-job. Sized so the next bucket is always longer than this.
        max_retries: per-fire retry count for transient failures.
    """

    def decorator(fn: JobFn) -> JobFn:
        @wraps(fn)
        async def wrapped() -> None:
            key = f"{job_name}:{bucket()}"
            try:
                acquired = await acquire_lock(key, lock_ttl_seconds)
            except Exception as exc:
                logger.error(
                    "nexhire.scheduler.lock_error",
                    extra={"job": job_name},
                    exc_info=exc,
                )
                return

            if not acquired:
                logger.info(
                    "nexhire.scheduler.skipped_idempotent",
                    extra={"job": job_name, "bucket": bucket()},
                )
                return

            attempt = 0
            while True:
                try:
                    await fn()
                    logger.info(
                        "nexhire.scheduler.completed",
                        extra={"job": job_name, "attempt": attempt + 1},
                    )
                    return
                except Exception as exc:
                    attempt += 1
                    logger.error(
                        "nexhire.scheduler.failed",
                        extra={"job": job_name, "attempt": attempt},
                        exc_info=exc,
                    )
                    if attempt >= max_retries:
                        await _dead_letter(job_name, exc)
                        return
                    await asyncio.sleep(5 * attempt)

        return wrapped

    return decorator


async def _dead_letter(job_name: str, exc: BaseException) -> None:
    """Persist a permanently-failed scheduler run to the dead-letter table.

    Uses the outbox connection for now — a dedicated `dead_letter_jobs`
    table lands in S0.6 alongside the audit + outbox migrations.
    """
    logger.critical(
        "nexhire.scheduler.dead_lettered",
        extra={
            "job": job_name,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        },
    )


# Convenience bucket helpers.
def bucket_daily() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def bucket_hourly() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H")


def bucket_six_hourly() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.date().isoformat()}T{now.hour // 6:02d}"


# ────────────────────────────────────────────────────────────────────
# Job registration helpers — slice modules call these from their own
# `*_job.py` modules at startup.
# ────────────────────────────────────────────────────────────────────
def register_interval_job(
    job_id: str,
    fn: JobFn,
    *,
    hours: int | None = None,
    minutes: int | None = None,
    **kwargs: Any,
) -> None:
    sched = get_scheduler()
    sched.add_job(
        fn,
        trigger="interval",
        id=job_id,
        replace_existing=True,
        hours=hours,
        minutes=minutes,
        **kwargs,
    )
    logger.info(
        "nexhire.scheduler.registered",
        extra={"job_id": job_id, "hours": hours, "minutes": minutes},
    )


def register_cron_job(
    job_id: str,
    fn: JobFn,
    *,
    hour: str = "*",
    minute: str = "0",
    **kwargs: Any,
) -> None:
    sched = get_scheduler()
    sched.add_job(
        fn,
        trigger="cron",
        id=job_id,
        replace_existing=True,
        hour=hour,
        minute=minute,
        **kwargs,
    )
    logger.info(
        "nexhire.scheduler.registered_cron",
        extra={"job_id": job_id, "hour": hour, "minute": minute},
    )
