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
from app.middleware import audit
from app.modules.onboarding import magic_link
from app.shared.constants import AI_SYSTEM_USER_ID
from app.shared.domain_events import ReferralApproved
from app.shared.exceptions import BusinessRuleError

logger = logging.getLogger("nexhire.onboarding.handlers")


async def on_referral_approved(event: ReferralApproved) -> None:
    factory = get_sessionmaker()
    try:
        async with factory() as session, session.begin():
            await magic_link.provision_candidate(
                session,
                referral_id=event.referral_id,
                candidate_email=event.candidate_email,
                candidate_name=event.candidate_name,
            )
    except BusinessRuleError as exc:
        # E.g. CANDIDATE_EMAIL_COLLISION — the candidate's email is
        # already a user with a different role. The referral remains
        # APPROVED in the DB; HR must resolve the email collision before
        # the candidate can be provisioned.
        logger.error(
            "nexhire.onboarding.candidate_provision_rejected",
            extra={
                "referral_id": str(event.referral_id),
                "candidate_email": event.candidate_email,
                "details": exc.details,
            },
        )
        await audit.publish(
            event_type="CANDIDATE_PROVISION_REJECTED",
            entity_type="REFERRAL",
            entity_id=event.referral_id,
            actor_user_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            payload={
                "candidate_email": event.candidate_email,
                "reason": exc.details,
                "message": exc.user_message,
            },
        )
        return
    logger.info(
        "nexhire.onboarding.candidate_provisioned",
        extra={"referral_id": str(event.referral_id)},
    )


def register(bus: InProcessEventBus) -> None:
    bus.subscribe(ReferralApproved, on_referral_approved)
