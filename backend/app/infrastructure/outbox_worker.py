"""Outbox retry worker.

The in-process event bus (Blueprint §17.9) catches per-handler failures
and persists `(event, handler)` pairs to `outbox_events`. This worker
reads PENDING rows every 2 minutes, replays them through the bus, and
either marks them PROCESSED or bumps `retry_count`. After 5 failures
the row goes to DEAD_LETTERED and an alert fires.

S2 only re-invokes the *original* handler that failed by name. Future
slices may add multi-handler outboxes; the design accommodates that
already (one outbox row per failed (event, handler) pair).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.outbox_models import OutboxEvent, OutboxStatus
from app.infrastructure.scheduler import (
    bucket_hourly,
    idempotent_job,
    register_interval_job,
)
from app.shared import domain_events as events_module

logger = logging.getLogger("nexhire.outbox.worker")

MAX_RETRIES = 5
BATCH_SIZE = 50


@idempotent_job(
    "outbox_retry",
    bucket=bucket_hourly,
    lock_ttl_seconds=120,
)
async def process_outbox() -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        rows = await _fetch_pending(session, limit=BATCH_SIZE)
        if not rows:
            return
        logger.info("nexhire.outbox.worker_run", extra={"pending": len(rows)})
        for row in rows:
            await _retry_one(session, row)


async def _fetch_pending(
    session: AsyncSession, *, limit: int
) -> list[OutboxEvent]:
    rows = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.PENDING.value)
        .where(OutboxEvent.retry_count < MAX_RETRIES)
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def _retry_one(session: AsyncSession, row: OutboxEvent) -> None:
    """Attempt to replay a single outbox entry.

    We import the event class dynamically from `app.shared.domain_events`
    by name, hydrate it from the persisted JSON payload, then look up the
    handler function/class on its declaring module. Failure → bump
    retry_count; if it crosses MAX_RETRIES → DEAD_LETTERED.
    """
    now = datetime.now(timezone.utc)
    try:
        event = _hydrate_event(row)
        handler = _resolve_handler(row.handler_class)
        await handler(event)
    except Exception as exc:  # noqa: BLE001 — outbox retry is best-effort
        row.retry_count += 1
        row.last_error = str(exc)[:1_000]
        if row.retry_count >= MAX_RETRIES:
            row.status = OutboxStatus.DEAD_LETTERED.value
            row.dead_lettered_at = now
            logger.error(
                "nexhire.outbox.dead_lettered",
                extra={
                    "outbox_id": row.id,
                    "event_type": row.event_type,
                    "handler": row.handler_class,
                    "retries": row.retry_count,
                },
            )
        else:
            logger.warning(
                "nexhire.outbox.retry_failed",
                extra={
                    "outbox_id": row.id,
                    "event_type": row.event_type,
                    "retries": row.retry_count,
                },
            )
        return

    row.status = OutboxStatus.PROCESSED.value
    row.processed_at = now


def _hydrate_event(row: OutboxEvent) -> Any:
    """Reconstruct an event dataclass from the persisted JSON payload.

    The payload was produced by `event_bus._serialize` which stringifies
    UUIDs + datetimes. Most fields take string-typed UUIDs cleanly; the
    dataclass `__init__` will validate.
    """
    cls = getattr(events_module, row.event_type, None)
    if cls is None or not hasattr(cls, "__dataclass_fields__"):
        raise ValueError(f"Unknown event type: {row.event_type}")
    payload = json.loads(row.payload)
    init_args = {
        k: v
        for k, v in payload.items()
        if k in cls.__dataclass_fields__
    }
    return cls(**init_args)


def _resolve_handler(qualname: str):  # type: ignore[no-untyped-def]
    """Re-resolve a `handler.__qualname__` to its callable.

    Handler qualnames come from the bus's `_invoke` and look like
    `on_referral_submitted` or `NexHireSomeClass.handle`. We only
    resolve module-level functions in S1–S2; class-based handlers
    aren't used yet.
    """
    # Module path is implicit; we search the registered handler modules.
    candidates = (
        "app.modules.notification.event_handlers",
        "app.modules.workflow.event_handlers",
    )
    for module_path in candidates:
        import importlib

        module = importlib.import_module(module_path)
        target = getattr(module, qualname, None)
        if callable(target):
            return target
    raise LookupError(f"Handler {qualname!r} not found in known modules")


def register() -> None:
    """Wire into APScheduler."""
    register_interval_job("outbox_retry", process_outbox, minutes=2)
