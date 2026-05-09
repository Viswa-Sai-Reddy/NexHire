"""Lifecycle event handlers — closure → certificate auto-send → CLOSED."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import get_bus
from app.infrastructure.event_bus import InProcessEventBus
from app.middleware import audit
from app.modules.ai import certificate
from app.modules.lifecycle import service as lifecycle_service
from app.modules.referral import cooling_period_service
from app.modules.onboarding.models import Intern
from app.modules.referral.models import Referral, ReferralStageHistory
from app.shared.constants import AI_SYSTEM_USER_ID, InternStatus, ReferralStatus

logger = logging.getLogger("nexhire.lifecycle.handlers")


async def on_closure_pending(event: lifecycle_service.ClosurePending) -> None:
    """Run AI-8 certificate generation; if auto-sent, move to CLOSED
    and apply RULE-CP6 (3-month re-join spacing).
    """
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        # Force auto-send (threshold=0.0) so the PDF is always generated
        # and the closure always advances to CLOSED — eliminates the
        # HR-review fallback for low-confidence citations.
        action = await certificate.auto_send_for_intern(
            session, intern_id=event.intern_id, confidence_threshold=0.0
        )
        if action.decision != "EXECUTED":
            logger.warning(
                "nexhire.lifecycle.cert_auto_send_skipped",
                extra={
                    "intern_id": str(event.intern_id),
                    "decision": action.decision,
                },
            )
            return

        referral = (
            await session.execute(
                select(Referral).where(Referral.id == event.referral_id)
            )
        ).scalar_one()
        intern = (
            await session.execute(
                select(Intern).where(Intern.id == event.intern_id)
            )
        ).scalar_one()
        now = datetime.now(UTC)
        referral.status = ReferralStatus.CLOSED.value
        referral.current_stage = ReferralStatus.CLOSED.value
        referral.stage_entered_at = now
        referral.updated_at = now
        # Keep intern.status in sync with referral.status — without this,
        # the mentor workspace shows the wrong tab/buttons and the
        # candidate's "Download certificate" panel never appears.
        intern.status = InternStatus.CLOSED.value
        intern.updated_at = now

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

    # Publish the domain event AFTER the closure transaction commits, so
    # downstream subscribers (notification → certificate-delivery email)
    # see the CLOSED row when they open their own session.
    await get_bus().publish(
        lifecycle_service.InternshipClosed(
            intern_id=event.intern_id,
            referral_id=event.referral_id,
        )
    )


def register(bus: InProcessEventBus) -> None:
    bus.subscribe(lifecycle_service.ClosurePending, on_closure_pending)
