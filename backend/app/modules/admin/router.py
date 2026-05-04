"""Admin router — S23, S24, S25 backend.

Endpoints:
  GET  /admin/overview              — executive dashboard data feed
  GET  /admin/audit/recent          — recent audit events (S24)
  GET  /admin/sla/open              — open SLA breaches (S24)
  GET  /admin/config/mentor-threshold
  POST /admin/config/mentor-threshold
  GET  /admin/config/cooling-periods
  POST /admin/config/cooling-periods/{state}
  GET  /admin/config/history
  POST /admin/chatbot               — AI-9
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.admin import config_service, dashboard_service
from app.modules.ai import program_chatbot
from app.modules.auth.rbac import Permission, require


admin_router = APIRouter(prefix="/admin", tags=["admin"])


class OverviewResponse(BaseModel):
    pipeline: dict[str, int]
    sla_breaches_open: int
    cooling_active: int
    at_risk: int


class MentorThresholdRequest(BaseModel):
    new_value: int = Field(..., ge=1, le=10)
    reason: str | None = Field(None, max_length=2000)


class CoolingPeriodRequest(BaseModel):
    new_duration_months: int = Field(..., ge=0, le=24)
    reason: str | None = Field(None, max_length=2000)


class CoolingPeriodEntry(BaseModel):
    terminal_state: str
    duration_months: int
    description: str
    set_by: UUID | None = None
    reason: str | None = None


class ChatbotRequest(BaseModel):
    question: str = Field(..., min_length=4, max_length=400)


class ChatbotResponse(BaseModel):
    answer: str
    data_source: str
    confidence: str


# ────────────────────────────────────────────────────────────────────
# Dashboards.
# ────────────────────────────────────────────────────────────────────
@admin_router.get(
    "/overview",
    response_model=OverviewResponse,
    dependencies=[Depends(require(Permission.VIEW_SLA_DASHBOARD))],
)
async def overview(
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    data = await dashboard_service.executive_overview(session)
    return OverviewResponse(**data)


@admin_router.get(
    "/audit/recent",
    dependencies=[Depends(require(Permission.VIEW_AUDIT_TRAIL))],
)
async def audit_recent(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await dashboard_service.audit_recent(session)


@admin_router.get(
    "/sla/open",
    dependencies=[Depends(require(Permission.VIEW_SLA_DASHBOARD))],
)
async def sla_open(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await dashboard_service.sla_breach_drilldown(session)


# ────────────────────────────────────────────────────────────────────
# Config panel (PO only — Permission.SYSTEM_CONFIGURATION).
# ────────────────────────────────────────────────────────────────────
@admin_router.get(
    "/config/mentor-threshold",
    dependencies=[Depends(require(Permission.SYSTEM_CONFIGURATION))],
)
async def get_mentor_threshold(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    return {"max_mentees": await config_service.get_mentor_threshold(session)}


@admin_router.post(
    "/config/mentor-threshold",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SYSTEM_CONFIGURATION)),
    ],
)
async def set_mentor_threshold_endpoint(
    body: MentorThresholdRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    new_value = await config_service.set_mentor_threshold(
        session,
        new_value=body.new_value,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        reason=body.reason,
    )
    return {"max_mentees": new_value}


@admin_router.get(
    "/config/cooling-periods",
    dependencies=[Depends(require(Permission.SYSTEM_CONFIGURATION))],
    response_model=list[CoolingPeriodEntry],
)
async def list_cooling_periods(
    session: AsyncSession = Depends(get_session),
) -> list[CoolingPeriodEntry]:
    rows = await config_service.list_cooling_periods(session)
    return [
        CoolingPeriodEntry(
            terminal_state=r.terminal_state,
            duration_months=r.duration_months,
            description=r.description,
            set_by=r.set_by,
            reason=r.reason,
        )
        for r in rows
    ]


@admin_router.post(
    "/config/cooling-periods/{terminal_state}",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SYSTEM_CONFIGURATION)),
    ],
)
async def set_cooling_period_endpoint(
    terminal_state: str,
    body: CoolingPeriodRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    new_value = await config_service.set_cooling_period(
        session,
        terminal_state=terminal_state,
        new_duration_months=body.new_duration_months,
        actor_user_id=principal.user_id,
        actor_role=principal.role,
        reason=body.reason,
    )
    return {"terminal_state": terminal_state, "duration_months": new_value}


@admin_router.get(
    "/config/history",
    dependencies=[Depends(require(Permission.SYSTEM_CONFIGURATION))],
)
async def config_history(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await config_service.list_history(session)


# ────────────────────────────────────────────────────────────────────
# AI-9 chatbot.
# ────────────────────────────────────────────────────────────────────
@admin_router.post(
    "/chatbot",
    response_model=ChatbotResponse,
    dependencies=[
        Depends(rate_limit("ai")),
        Depends(require(Permission.QUERY_AI_CHATBOT)),
    ],
)
async def chatbot(
    body: ChatbotRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatbotResponse:
    answer = await program_chatbot.ask(session, question=body.question)
    return ChatbotResponse(
        answer=answer.answer,
        data_source=answer.data_source,
        confidence=answer.confidence,
    )
