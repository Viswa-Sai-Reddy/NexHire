"""Workflow event handlers.

Subscribed at app startup via `app.wiring.register_all`. The handlers
own *cross-module reactions*:
  * MentorAccepted → run the auto-approval engine.

The handler opens its own session — by the time the bus invokes it,
the originating transaction (mentor.accept) has committed, so we
need a fresh transaction to mutate state.
"""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.workflow import auto_approval
from app.shared.domain_events import MentorAccepted

logger = logging.getLogger("nexhire.workflow.handlers")


async def on_mentor_accepted(event: MentorAccepted) -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        try:
            result = await auto_approval.evaluate_and_route(
                session, referral_id=event.referral_id
            )
        except Exception:
            logger.exception(
                "nexhire.workflow.auto_approval_failed",
                extra={"referral_id": str(event.referral_id)},
            )
            raise
    logger.info(
        "nexhire.workflow.auto_approval_done",
        extra={
            "referral_id": str(event.referral_id),
            "decision": result.decision,
            "flags": list(result.flags),
            "recommendation": result.hr_recommendation,
        },
    )


def register(bus: InProcessEventBus) -> None:
    bus.subscribe(MentorAccepted, on_mentor_accepted)
