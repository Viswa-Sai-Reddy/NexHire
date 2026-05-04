"""Lifecycle event handlers — closure → certificate auto-send → CLOSED."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.middleware import audit
from app.modules.ai import certificate
from app.modules.lifecycle import service as lifecycle_service
from app.modules.referral import cooling_period_service
from app.modules.referral.models import Referral, ReferralStageHistory
from app.shared.constants import AI_SYSTEM_USER_ID, ReferralStatus

logger = logging.getLogger("nexhire.lifecycle.handlers")


async def on_closure_pending(event: lifecycle_service.ClosurePending) -> None:
    """Run AI-8 certificate generation; if auto-sent, move to CLOSED
    and apply RULE-CP6 (3-month re-join spacing).
    """
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        action = await certificate.auto_send_for_intern(
            session, intern_id=event.intern_id
        )
        if action.decision != "EXECUTED":
            return  # HR review path; manual closure happens later

        referral = (
            await session.execute(
                select(Referral).where(Referral.id == event.referral_id)
            )
        ).scalar_one()
        now = datetime.now(timezone.utc)
        referral.status = ReferralStatus.CLOSED.value
        referral.current_stage = ReferralStatus.CLOSED.value
        referral.stage_entered_at = now
        referral.updated_at = now

        session.add(
            ReferralStageHistory(
                referral_id=referral.id,
                from_status=ReferralStatus.CLOSURE_PENDING.value,
                to_status=ReferralStatus.CLOSED.value,
                actor_id=AI_SYSTEM_USER_ID,
                actor_role="SYSTEM",
                reason="Certificate auto-sent; clean closure complete.",
            )
        )

        await cooling_period_service.apply(
            session,
            referral_id=referral.id,
            terminal_state=ReferralStatus.CLOSED.value,
        )
        await audit.publish(
            event_type="INTERNSHIP_CLOSED",
            entity_type="INTERN",
            entity_id=event.intern_id,
            actor_user_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            payload={"closed_by": "AI_AUTO_SEND_CERT"},
            session=session,
        )


def register(bus: InProcessEventBus) -> None:
    bus.subscribe(lifecycle_service.ClosurePending, on_closure_pending)
