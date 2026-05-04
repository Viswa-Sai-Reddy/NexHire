"""Audit checksum chain — concurrency safety + integrity verification.

S0 acceptance criterion (Implementation_Plan.md):
  > Audit checksum chain validated by an integration test that inserts
  > 100 events concurrently.

This is the test. We fire off 100 concurrent `audit.publish()` calls,
each with a unique payload, then walk the chain forward and assert it's
intact. Without `pg_advisory_xact_lock` this would either deadlock on
the unique-checksum index or fork the chain.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit


@pytest.mark.asyncio
async def test_chain_remains_intact_under_concurrent_writes(
    session: AsyncSession,
) -> None:
    n = 100

    async def one(i: int) -> None:
        await audit.publish(
            event_type="SMOKE_TEST",
            entity_type="HEARTBEAT",
            entity_id=uuid4(),
            actor_role="SYSTEM",
            payload={"i": i, "note": f"event-{i}"},
        )

    await asyncio.gather(*(one(i) for i in range(n)))

    # Total rows.
    total = (
        await session.execute(text("SELECT COUNT(*) FROM audit_events"))
    ).scalar_one()
    assert total >= n  # may be > n if other tests already inserted

    # Chain must verify end-to-end.
    intact = await audit.verify_chain(session)
    assert intact, "Audit checksum chain is broken under concurrent writes."


@pytest.mark.asyncio
async def test_business_rule_violation_is_audited(session: AsyncSession) -> None:
    """Business-rule errors land in audit_events even when the request
    fails (Blueprint §17.4 last paragraph).
    """
    from app.shared.exceptions import CollegeCapExceededError

    exc = CollegeCapExceededError(college="VIT Vellore")
    await audit.audit_business_rule_violation(exc, path="/api/v1/referrals")

    row = (
        await session.execute(
            text(
                "SELECT event_type, payload "
                "FROM audit_events "
                "WHERE event_type = 'BUSINESS_RULE_VIOLATED' "
                "ORDER BY id DESC LIMIT 1"
            )
        )
    ).mappings().first()

    assert row is not None
    assert row["event_type"] == "BUSINESS_RULE_VIOLATED"
    assert row["payload"]["code"] == "COLLEGE_CAP_EXCEEDED"
    assert row["payload"]["rule_id"] == "RULE-E2"
    assert row["payload"]["details"]["college"] == "VIT Vellore"
