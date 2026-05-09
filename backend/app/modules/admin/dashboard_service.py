"""Read-side aggregations for S23 (Executive) and S24 (Audit/SLA)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def executive_overview(session: AsyncSession) -> dict[str, Any]:
    pipeline = (
        await session.execute(
            text("SELECT status, COUNT(*) FROM referrals GROUP BY status")
        )
    ).all()
    pipeline_counts = {str(s): int(c) for s, c in pipeline}

    sla_breaches = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) FROM tasks
                WHERE status NOT IN ('COMPLETED','CANCELLED')
                  AND sla_deadline < NOW()
                """
            )
        )
    ).scalar_one()

    cooling_active = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) FROM referrals
                WHERE cooling_period_end_at > NOW()
                  AND cooling_override_at IS NULL
                """
            )
        )
    ).scalar_one()

    at_risk = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT ON (referral_id) referral_id, raw_output
                  FROM ai_parse_results
                  WHERE ai_touchpoint = 'BOTTLENECK_PREDICTION'
                  ORDER BY referral_id, parsed_at DESC
                ) sub
                WHERE (raw_output ->> 'risk')::float >= 0.4
                """
            )
        )
    ).scalar_one()

    return {
        "pipeline": pipeline_counts,
        "sla_breaches_open": int(sla_breaches),
        "cooling_active": int(cooling_active),
        "at_risk": int(at_risk),
    }


async def audit_recent(
    session: AsyncSession, *, limit: int = 100, since_hours: int = 168
) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
    rows = (
        await session.execute(
            text(
                """
                SELECT event_type, entity_type, entity_id, actor_user_id,
                       actor_role, event_timestamp, payload
                FROM audit_events
                WHERE event_timestamp >= :cutoff
                ORDER BY id DESC
                LIMIT :limit
                """
            ).bindparams(cutoff=cutoff, limit=limit)
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def sla_breach_drilldown(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, task_type, intern_id, referral_id,
                       assigned_to, sla_deadline, status,
                       EXTRACT(EPOCH FROM (NOW() - sla_deadline))/3600 AS hours_overdue
                FROM tasks
                WHERE status NOT IN ('COMPLETED','CANCELLED')
                  AND sla_deadline < NOW()
                ORDER BY sla_deadline ASC
                LIMIT 100
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["audit_recent", "executive_overview", "sla_breach_drilldown"]
