"""Onboarding event handlers.

  * `ReferralApproved` (HR or AI auto-approval) → provision candidate
    user + intern + first magic-link token. Notification module also
    subscribes (S5) to email the candidate; the magic-link token is
    placed inside the email body.
  * `JoiningFormLocked` → auto-generate Non-Worker ID + advance status.
"""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.onboarding import auto_lock, magic_link, service
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
    bus.subscribe(auto_lock.JoiningFormLocked, service.on_joining_form_locked)
