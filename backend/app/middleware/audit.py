"""Audit publisher with tamper-evident checksum chain.

This is the most security-critical subsystem in NexHire. Direct
implementation of Blueprint §9.1 + §17.12 + decision B9.

Chain construction:

    event_n.checksum = SHA-256( event_{n-1}.checksum || canonical(event_n.payload) )
    event_0.checksum = SHA-256( "GENESIS" || canonical(event_0.payload) )

Concurrency: the chain MUST be serial. Two parallel inserts both reading
"current latest checksum" would produce a fork. We serialize on insert
using `pg_advisory_xact_lock(AUDIT_CHAIN_LOCK_KEY)` — the lock is
released automatically when the enclosing transaction ends.

Immutability: at the DB level, application role has `INSERT` only. A
nightly job (S6) walks the chain and asserts integrity end-to-end.

`canonical(...)` here is `json.dumps(payload, sort_keys=True,
separators=(",", ":"), default=str)`. Stability of this serialization
is critical — changing it would invalidate the historical chain.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_sessionmaker
from app.middleware.logging import actor_user_id_ctx, request_id_ctx
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    AUDIT_CHAIN_LOCK_KEY,
    GENESIS_CHECKSUM,
)
from app.shared.exceptions import AuditLogFailureError, BusinessRuleError

logger = logging.getLogger("nexhire.audit")


def _canonical_json(payload: dict[str, Any]) -> str:
    """Stable JSON serialization. Used by both write + verify paths.

    Ordering: keys sorted lexicographically.
    Whitespace: none.
    Non-JSON types: stringified via `default=str` (UUIDs, datetimes).
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def _persist(
    session: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: UUID | None,
    actor_user_id: UUID | None,
    actor_role: str | None,
    ip_address: str | None,
    user_agent: str | None,
    payload: dict[str, Any],
) -> int:
    """Insert one audit row inside the caller's transaction.

    The advisory lock is acquired *inside* the same transaction so it
    auto-releases on commit / rollback. Anyone else trying to insert
    must wait until we're done.
    """
    # 1. Serialize on the chain.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=AUDIT_CHAIN_LOCK_KEY)
    )

    # 2. Read the latest checksum (after the lock — guaranteed monotonic).
    latest = (
        await session.execute(
            text(
                "SELECT checksum FROM audit_events "
                "ORDER BY id DESC LIMIT 1 FOR UPDATE"
            )
        )
    ).scalar_one_or_none()
    prev_checksum = latest if latest is not None else GENESIS_CHECKSUM

    # 3. Compute this row's checksum.
    canonical_payload = _canonical_json(payload)
    checksum = _sha256(prev_checksum + canonical_payload)

    # 4. Insert. `id` is BIGSERIAL — Postgres assigns it.
    result = await session.execute(
        text(
            """
            INSERT INTO audit_events (
                event_type, entity_type, entity_id,
                actor_user_id, actor_role,
                ip_address, user_agent,
                event_timestamp, payload,
                prev_checksum, checksum
            ) VALUES (
                :event_type, :entity_type, CAST(:entity_id AS uuid),
                CAST(:actor_user_id AS uuid), :actor_role,
                CAST(:ip_address AS inet), :user_agent,
                :event_timestamp, CAST(:payload AS jsonb),
                :prev_checksum, :checksum
            )
            RETURNING id
            """
        ).bindparams(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            actor_user_id=str(actor_user_id) if actor_user_id else None,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
            event_timestamp=datetime.now(UTC),
            payload=canonical_payload,
            prev_checksum=prev_checksum,
            checksum=checksum,
        )
    )
    row_id = result.scalar_one()
    return int(row_id)


async def publish(
    *,
    event_type: str,
    entity_type: str,
    entity_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    actor_role: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    payload: dict[str, Any] | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Append one audit event.

    Args:
        event_type: e.g. "REFERRAL_SUBMITTED".
        entity_type: e.g. "REFERRAL". Free string by convention.
        entity_id: PK of the affected entity.
        actor_user_id: who did it. Falls back to `actor_user_id_ctx`.
            For scheduler-driven events pass `AI_SYSTEM_USER_ID`.
        session: optional — if supplied, the audit row is appended
            inside the caller's transaction (preferred). Otherwise we
            open a brief transaction of our own.

    Raises:
        AuditLogFailureError: writing the audit row failed. The caller
        must abort the surrounding operation — Blueprint §17.12 makes
        audit integrity a fail-stop concern.
    """
    payload = payload or {}
    # Best-effort actor inference.
    if actor_user_id is None:
        ctx = actor_user_id_ctx.get()
        if ctx:
            try:
                actor_user_id = UUID(ctx)
            except ValueError:
                actor_user_id = None

    rid = request_id_ctx.get()
    if rid and "request_id" not in payload:
        payload = {**payload, "request_id": rid}

    try:
        if session is not None:
            return await _persist(
                session,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                ip_address=ip_address,
                user_agent=user_agent,
                payload=payload,
            )
        # Stand-alone session.
        factory = get_sessionmaker()
        async with factory() as own_session, own_session.begin():
            return await _persist(
                own_session,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                ip_address=ip_address,
                user_agent=user_agent,
                payload=payload,
            )
    except Exception as exc:
        logger.critical(
            "nexhire.audit.write_failed",
            extra={"event_type": event_type, "entity_type": entity_type},
            exc_info=exc,
        )
        # Surface as a fatal SystemError. The error handler will return
        # 500 with code AUDIT_LOG_FAILURE and the surrounding operation
        # will be rolled back by the caller's `try/except`.
        raise AuditLogFailureError() from exc


# ────────────────────────────────────────────────────────────────────
# Public helper used by the global error handler.
# Keeps the audit policy ("every business rule violation is audited")
# in one place rather than re-encoded at each call site.
# ────────────────────────────────────────────────────────────────────
async def audit_business_rule_violation(
    exc: BusinessRuleError, *, path: str
) -> None:
    await publish(
        event_type="BUSINESS_RULE_VIOLATED",
        entity_type="HTTP_REQUEST",
        entity_id=None,
        actor_role=None,
        payload={
            "code": exc.code,
            "rule_id": exc.rule_id,
            "path": path,
            "message": exc.user_message,
            "details": exc.details,
        },
    )


# ────────────────────────────────────────────────────────────────────
# Scheduler / background convenience: events emitted by jobs use the
# AI_SYSTEM actor (decision E15).
# ────────────────────────────────────────────────────────────────────
async def publish_system_event(
    *,
    event_type: str,
    entity_type: str,
    entity_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    return await publish(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload=payload,
    )


# ────────────────────────────────────────────────────────────────────
# Verification — used by the nightly integrity check (S6) and the
# concurrent-write smoke test (S0.7).
# ────────────────────────────────────────────────────────────────────
async def verify_chain(session: AsyncSession, *, batch_size: int = 1000) -> bool:
    """Walk the chain end-to-end. Returns True iff intact."""
    offset = 0
    expected_prev = GENESIS_CHECKSUM
    while True:
        rows = (
            await session.execute(
                text(
                    "SELECT id, payload::text AS payload, prev_checksum, checksum "
                    "FROM audit_events ORDER BY id ASC LIMIT :limit OFFSET :offset"
                ).bindparams(limit=batch_size, offset=offset)
            )
        ).mappings().all()
        if not rows:
            return True
        for row in rows:
            if row["prev_checksum"] != expected_prev:
                logger.error(
                    "nexhire.audit.chain_broken",
                    extra={"row_id": row["id"], "expected_prev": expected_prev},
                )
                return False
            recomputed = _sha256(row["prev_checksum"] + row["payload"])
            if recomputed != row["checksum"]:
                logger.error(
                    "nexhire.audit.checksum_mismatch",
                    extra={"row_id": row["id"]},
                )
                return False
            expected_prev = row["checksum"]
        offset += batch_size
