"""Event-bus smoke: publish + handler isolation + outbox-on-failure.

Acceptance criterion (S0):
  > Event bus publishes a `Heartbeat` event handled by a noop subscriber
  > in a test.

We additionally cover handler-isolation (one failing handler doesn't
silence others) and outbox persistence (failed handlers leave a row
the retry worker can pick up).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import reset_bus_for_tests
from app.shared.domain_events import Heartbeat


@pytest.mark.asyncio
async def test_handler_invoked() -> None:
    bus = reset_bus_for_tests()
    seen: list[str] = []

    async def handler(event: Heartbeat) -> None:
        seen.append(event.note)

    bus.subscribe(Heartbeat, handler)

    await bus.publish(Heartbeat(note="hello"))

    assert seen == ["hello"]


@pytest.mark.asyncio
async def test_handler_failure_does_not_block_peers(session: AsyncSession) -> None:
    bus = reset_bus_for_tests()
    seen: list[str] = []

    async def good(event: Heartbeat) -> None:
        seen.append(event.note)

    async def bad(_event: Heartbeat) -> None:
        raise RuntimeError("simulated failure")

    bus.subscribe(Heartbeat, good)
    bus.subscribe(Heartbeat, bad)

    await bus.publish(Heartbeat(note="resilience-check"))

    # Good handler still ran.
    assert seen == ["resilience-check"]

    # Bad handler's failure persisted to the outbox.
    row = (
        await session.execute(
            text(
                "SELECT event_type, status, last_error "
                "FROM outbox_events "
                "ORDER BY id DESC LIMIT 1"
            )
        )
    ).mappings().first()
    assert row is not None
    assert row["event_type"] == "Heartbeat"
    assert row["status"] == "PENDING"
    assert "simulated failure" in row["last_error"]
