"""Onboarding event handlers.

  * `ReferralApproved` (HR or AI auto-approval) → provision candidate
    user + intern + first magic-link token. Notification module also
    subscribes (S5) to email the candidate; the magic-link token is
    placed inside the email body.

NW-ID generation no longer runs as a `JoiningFormLocked` handler — it
runs inline inside `auto_lock._auto_lock` so it shares the lock's
transaction (silent rollbacks were leaving candidates locked but
without a Non-Worker ID).
"""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.onboarding import magic_link
from app.shared.domain_events import ReferralApproved

logger = logging.getLogger("nexhire.onboarding.handlers")


async def on_referral_approved(event: ReferralApproved) -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        await magic_link.provision_candidate(
            session,
            referral_id=event.referral_id,
            candidate_email=event.candidate_email,
            candidate_name=event.candidate_name,
        )
    logger.info(
        "nexhire.onboarding.candidate_provisioned",
        extra={"referral_id": str(event.referral_id)},
    )


def register(bus: InProcessEventBus) -> None:
    bus.subscribe(ReferralApproved, on_referral_approved)
