"""In-process async event bus with transactional outbox.

Cross-module communication contract (Blueprint §8.2 Rule 1):

    publisher  ─publish(event)──►  bus  ──►  registered handlers
                                            │
                            on handler error│
                                            ▼
                                  outbox_events table
                                            │
                                  worker job retries
                                            ▼
                                       handler again

Why an outbox: handlers are best-effort within a request. If the
notification handler fails to send an email because Gmail is down, the
referral submission still succeeded — we don't want the user's POST to
fail. The outbox captures failures and retries them later, with bounded
retries before dead-letter.

Order of operations matters:
  1. Service writes its own state to DB (the "happens-before").
  2. Service publishes the event.
  3. The bus invokes each handler under its own try/except.
  4. Failed handlers go to the outbox.

This is NOT the full Transactional Outbox pattern (events are not
written to the DB *atomically* with the producer's state). For S0–S6
the simpler "publish then outbox-on-failure" model is sufficient given
the volume and the existing audit trail; a true transactional outbox
ships in Phase 2 when we extract the AI module (Blueprint §13.2).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, TypeVar

from app.shared.domain_events import DomainEvent

logger = logging.getLogger("nexhire.events")

EventT = TypeVar("EventT", bound=DomainEvent)
Handler = Callable[[EventT], Awaitable[None]]


def _serialize(event: DomainEvent) -> dict[str, Any]:
    """Turn a frozen-dataclass event into a JSON-safe dict for the outbox."""
    payload: dict[str, Any] = {}
    for key, value in asdict(event).items():
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        elif hasattr(value, "hex"):  # UUIDs
            payload[key] = str(value)
        else:
            payload[key] = value
    return payload


class InProcessEventBus:
    """Synchronous-from-the-publisher's-POV in-process bus.

    `publish` awaits all handlers concurrently. Any exception is caught
    per-handler so one failing handler can't take down the others. Failed
    invocations are persisted to `outbox_events` for the retry worker.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler[Any]]] = defaultdict(list)

    def subscribe(self, event_type: type[EventT], handler: Handler[EventT]) -> None:
        """Register `handler` for events of `event_type`.

        Modules call this at app-startup time from their
        `event_handlers.py`. Subscriptions are not persisted — they are
        re-registered on every process boot.
        """
        self._handlers[event_type].append(handler)
        logger.debug(
            "nexhire.events.subscribed",
            extra={"event_type": event_type.__name__, "handler": handler.__qualname__},
        )

    def handlers_for(self, event: DomainEvent) -> list[Handler[Any]]:
        """All handlers registered for this event's exact type. We do
        NOT walk the MRO — each event class declares its own contract.
        """
        return list(self._handlers.get(type(event), []))

    async def publish(self, event: DomainEvent) -> None:
        """Invoke every handler for `event`.

        If called inside a FastAPI request that has an active session,
        defer dispatch until *after* the request transaction commits.
        This way handlers that open their own session can see the rows
        the producer just wrote. Outside a request (e.g. scheduled jobs)
        run handlers immediately.

        Failures are isolated per handler; handlers run concurrently.
        """
        # Defer if there's an in-flight request session.
        from app.infrastructure.database import current_request_session

        active_session = current_request_session()
        if active_session is not None:
            queue = active_session.info.setdefault("after_commit", [])
            queue.append(lambda e=event: self._dispatch(e))
            logger.debug(
                "nexhire.events.deferred",
                extra={"event_type": event.event_type, "event_id": str(event.event_id)},
            )
            return

        await self._dispatch(event)

    async def _dispatch(self, event: DomainEvent) -> None:
        handlers = self.handlers_for(event)
        if not handlers:
            logger.debug(
                "nexhire.events.no_handlers",
                extra={"event_type": event.event_type, "event_id": str(event.event_id)},
            )
            return

        results = await asyncio.gather(
            *(self._invoke(h, event) for h in handlers),
            return_exceptions=True,
        )

        # Persist any failures to the outbox.
        for handler, outcome in zip(handlers, results, strict=True):
            if isinstance(outcome, BaseException):
                await self._enqueue_outbox(event, handler, outcome)

    async def _invoke(self, handler: Handler[Any], event: DomainEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            logger.error(
                "nexhire.events.handler_failed",
                extra={
                    "event_type": event.event_type,
                    "event_id": str(event.event_id),
                    "handler": handler.__qualname__,
                    "error": exc.__class__.__name__,
                },
                exc_info=exc,
            )
            raise

    async def _enqueue_outbox(
        self,
        event: DomainEvent,
        handler: Handler[Any],
        error: BaseException,
    ) -> None:
        """Persist a failed (event, handler) pair so the retry worker
        can pick it up.

        Imported lazily so the bus doesn't pull in the ORM at import time
        (keeps the kernel-y feel of `infrastructure/`).
        """
        from sqlalchemy import insert

        from app.infrastructure.database import get_sessionmaker

        try:
            from app.infrastructure.outbox_models import OutboxEvent

            factory = get_sessionmaker()
            async with factory() as session, session.begin():
                await session.execute(
                    insert(OutboxEvent).values(
                        event_type=event.event_type,
                        handler_class=handler.__qualname__,
                        payload=json.dumps(_serialize(event)),
                        status="PENDING",
                        retry_count=0,
                        last_error=str(error)[:1000],
                        created_at=datetime.now(UTC),
                    )
                )
            logger.info(
                "nexhire.events.outboxed",
                extra={
                    "event_type": event.event_type,
                    "handler": handler.__qualname__,
                },
            )
        except Exception:
            # If the outbox itself fails we have nothing more we can do.
            # Do NOT raise — we already failed once, raising here would
            # mask the original error from the publisher.
            logger.exception(
                "nexhire.events.outbox_persist_failed",
                extra={"event_type": event.event_type},
            )


# ────────────────────────────────────────────────────────────────────
# Singleton — wired in `app.main` lifespan; tests construct their own.
# ────────────────────────────────────────────────────────────────────
_bus: InProcessEventBus | None = None


def get_bus() -> InProcessEventBus:
    global _bus
    if _bus is None:
        _bus = InProcessEventBus()
    return _bus


def reset_bus_for_tests() -> InProcessEventBus:
    """Test-only escape hatch — wipes subscriptions."""
    global _bus
    _bus = InProcessEventBus()
    return _bus
