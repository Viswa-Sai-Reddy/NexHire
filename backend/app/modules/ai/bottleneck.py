"""AI-5 — Bottleneck predictor (F-27).

Phase-1 heuristics (Blueprint §7 AI-5):
  risk = (days_in_stage / historical_avg) × 0.5
       + (assigned_user_workload / 10)   × 0.3
       + 0.15 if Friday
       + 0.10 if upcoming holiday
       capped at 1.0

Runs every 6h via APScheduler. Writes one `ai_parse_results` row per
referral so the executive dashboard (S23) can read at-risk counts.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.referral.models import (
    AiParseResult,
    Referral,
    StageDurationStat,
)
from app.shared.constants import TERMINAL_REFERRAL_STATUSES, ReferralStatus

logger = logging.getLogger("nexhire.ai.bottleneck")

MODEL_TOUCHPOINT = "BOTTLENECK_PREDICTION"


class BottleneckPrediction(NamedTuple):
    referral_id: UUID
    risk: float
    classification: str  # ON_TRACK | AT_RISK | HIGH_RISK
    days_in_stage: int
    historical_avg_hours: float | None


async def predict_for_active_referrals(
    session: AsyncSession,
    *,
    today: date | None = None,
) -> list[BottleneckPrediction]:
    today = today or date.today()
    now = datetime.now(timezone.utc)

    # Pull stats once.
    stats_rows = (
        await session.execute(select(StageDurationStat))
    ).scalars().all()
    stats = {row.stage: row for row in stats_rows}

    # Active referrals.
    referrals = (
        await session.execute(
            select(Referral).where(
                Referral.status.notin_([s.value for s in TERMINAL_REFERRAL_STATUSES])
            )
        )
    ).scalars().all()

    is_friday = now.weekday() == 4
    upcoming_holiday = await _has_upcoming_holiday(session, today=today)

    predictions: list[BottleneckPrediction] = []
    for referral in referrals:
        days = max(0, (now.date() - referral.stage_entered_at.date()).days)
        stat = stats.get(referral.current_stage)
        avg_hours = stat.avg_hours if stat and stat.avg_hours else None
        avg_days = (avg_hours / 24.0) if avg_hours else None

        ratio = (days / avg_days) if avg_days and avg_days > 0 else (days / 5.0)
        workload = await _assigned_workload(session, referral_id=referral.id)
        risk = (
            min(ratio, 2.0) * 0.5
            + min(workload / 10.0, 1.0) * 0.3
            + (0.15 if is_friday else 0.0)
            + (0.10 if upcoming_holiday else 0.0)
        )
        risk = min(risk, 1.0)
        classification = (
            "HIGH_RISK" if risk > 0.7 else "AT_RISK" if risk >= 0.4 else "ON_TRACK"
        )
        predictions.append(
            BottleneckPrediction(
                referral_id=referral.id,
                risk=round(risk, 3),
                classification=classification,
                days_in_stage=days,
                historical_avg_hours=avg_hours,
            )
        )

        session.add(
            AiParseResult(
                ai_touchpoint=MODEL_TOUCHPOINT,
                model_version="rules:phase1:v1",
                referral_id=referral.id,
                raw_output={
                    "risk": round(risk, 3),
                    "classification": classification,
                    "days_in_stage": days,
                    "stage": referral.current_stage,
                },
                succeeded=True,
            )
        )
    return predictions


async def _assigned_workload(
    session: AsyncSession, *, referral_id: UUID
) -> int:
    """Heuristic: number of open tasks owned by anyone currently
    assigned to this referral (HR review + JF review). Doesn't need to
    be perfect — feeds a 0–1 risk dial.
    """
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(open_count), 0) AS w FROM (
              SELECT COUNT(*) AS open_count
              FROM tasks t
              WHERE t.assigned_to IN (
                SELECT assigned_to FROM tasks
                WHERE referral_id = :rid
                  AND status NOT IN ('COMPLETED','CANCELLED')
              )
                AND t.status NOT IN ('COMPLETED','CANCELLED')
              GROUP BY t.assigned_to
            ) sub
            """
        ).bindparams(rid=referral_id)
    )
    return int(row.scalar_one() or 0)


async def _has_upcoming_holiday(
    session: AsyncSession, *, today: date
) -> bool:
    from datetime import timedelta

    row = await session.execute(
        text(
            "SELECT 1 FROM holidays WHERE date BETWEEN :a AND :b LIMIT 1"
        ).bindparams(a=today, b=today + timedelta(days=3))
    )
    return row.first() is not None


__all__ = ["BottleneckPrediction", "MODEL_TOUCHPOINT", "predict_for_active_referrals"]


# Suppress unused-import warning when loaded standalone.
_ = ReferralStatus
