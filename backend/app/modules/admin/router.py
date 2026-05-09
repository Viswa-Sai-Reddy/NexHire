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
from datetime import UTC, datetime

from sqlalchemy import select

from app.infrastructure import azure_openai
from app.middleware import audit
from app.modules.admin import config_service, dashboard_service
from app.modules.ai import program_chatbot
from app.modules.auth.rbac import Permission, require
from app.modules.referral import cooling_period_service
from app.modules.referral.models import NotificationTemplate
from app.shared.constants import COOLING_OVERRIDE_MIN_REASON_LENGTH
from app.shared.exceptions import BusinessRuleError

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
# Cooling-period override (PO only — RULE-CP7).
# ────────────────────────────────────────────────────────────────────
class CoolingOverrideRequest(BaseModel):
    reason: str = Field(..., min_length=COOLING_OVERRIDE_MIN_REASON_LENGTH, max_length=2000)


@admin_router.post(
    "/cooling-overrides/{referral_id}",
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.OVERRIDE_COOLING_PERIOD)),
    ],
    summary="PO overrides the active cooling period on a terminal referral (RULE-CP7).",
)
async def cooling_override_endpoint(
    referral_id: UUID,
    body: CoolingOverrideRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await cooling_period_service.apply_override(
        session,
        referral_id=referral_id,
        program_owner_id=principal.user_id,
        program_owner_role=principal.role,
        reason=body.reason,
    )
    return {"referral_id": str(referral_id), "status": "OVERRIDDEN"}


# ────────────────────────────────────────────────────────────────────
# Notification template management.
# ────────────────────────────────────────────────────────────────────
class TemplateEntry(BaseModel):
    template_id: str
    subject: str
    is_active: bool
    updated_by: UUID | None
    updated_at: datetime
    created_at: datetime


class TemplateUpdateRequest(BaseModel):
    subject: str | None = Field(None, min_length=3, max_length=500)
    is_active: bool | None = None


@admin_router.get(
    "/notification-templates",
    response_model=list[TemplateEntry],
    dependencies=[Depends(require(Permission.SYSTEM_CONFIGURATION))],
    summary="List all notification templates (PO only).",
)
async def list_templates(
    session: AsyncSession = Depends(get_session),
) -> list[TemplateEntry]:
    rows = (
        await session.execute(
            select(NotificationTemplate).order_by(NotificationTemplate.template_id)
        )
    ).scalars().all()
    return [
        TemplateEntry(
            template_id=t.template_id,
            subject=t.subject,
            is_active=t.is_active,
            updated_by=t.updated_by,
            updated_at=t.updated_at,
            created_at=t.created_at,
        )
        for t in rows
    ]


@admin_router.patch(
    "/notification-templates/{template_id}",
    response_model=TemplateEntry,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SYSTEM_CONFIGURATION)),
    ],
    summary="Edit a notification template's subject or active flag (PO only).",
)
async def update_template(
    template_id: str,
    body: TemplateUpdateRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> TemplateEntry:
    template = (
        await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.template_id == template_id
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise BusinessRuleError(
            user_message=f"Notification template {template_id!r} not found."
        )

    changes: dict[str, Any] = {}
    if body.subject is not None and body.subject != template.subject:
        changes["subject"] = {"from": template.subject, "to": body.subject}
        template.subject = body.subject
    if body.is_active is not None and body.is_active != template.is_active:
        changes["is_active"] = {"from": template.is_active, "to": body.is_active}
        template.is_active = body.is_active

    if not changes:
        raise BusinessRuleError(
            user_message="No changes provided. Set subject and/or is_active."
        )

    now = datetime.now(UTC)
    template.updated_by = principal.user_id
    template.updated_at = now

    await audit.publish(
        event_type="NOTIFICATION_TEMPLATE_UPDATED",
        entity_type="NOTIFICATION_TEMPLATE",
        entity_id=None,  # template_id is a string PK; surface in payload
        actor_user_id=principal.user_id,
        actor_role=principal.role.value,
        payload={"template_id": template_id, "changes": changes},
        session=session,
    )

    return TemplateEntry(
        template_id=template.template_id,
        subject=template.subject,
        is_active=template.is_active,
        updated_by=template.updated_by,
        updated_at=template.updated_at,
        created_at=template.created_at,
    )


# ────────────────────────────────────────────────────────────────────
# AI usage snapshot (last N calls in-process — Application Insights
# remains the canonical aggregator once configured).
# ────────────────────────────────────────────────────────────────────
class AiUsageEntry(BaseModel):
    operation: str
    tokens_total: int | None
    latency_ms: int
    succeeded: bool


@admin_router.get(
    "/ai-usage",
    response_model=list[AiUsageEntry],
    dependencies=[Depends(require(Permission.VIEW_SLA_DASHBOARD))],
    summary="Last 100 Azure OpenAI calls (newest first) — debugging snapshot.",
)
async def ai_usage(limit: int = 100) -> list[AiUsageEntry]:
    return [
        AiUsageEntry(
            operation=e.operation,
            tokens_total=e.tokens_total,
            latency_ms=e.latency_ms,
            succeeded=e.succeeded,
        )
        for e in azure_openai.recent_usage(limit=limit)
    ]


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
