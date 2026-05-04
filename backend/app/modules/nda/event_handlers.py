"""NDA event subscriptions.

  * `JoiningFormLocked` (or HR manual lock fallback after Non-Worker
    ID auto-gen) → issue NDA. Onboarding's `service.on_joining_form_locked`
    runs first to allocate the NW-ID; this handler runs alongside.
  * `NdaSigned` → fire access-provisioning (S4 access service) +
    offer-letter auto-send.
"""
from __future__ import annotations

import logging

from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.access import service as access_service
from app.modules.nda import service as nda_service
from app.modules.onboarding.auto_lock import JoiningFormLocked
from app.modules.workflow import offer_letter

logger = logging.getLogger("nexhire.nda.handlers")


async def on_joining_form_locked_issue_nda(event: JoiningFormLocked) -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        await nda_service.issue_for_intern(session, intern_id=event.intern_id)


async def on_nda_signed(event: nda_service.NdaSigned) -> None:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        await access_service.request_access_provisioning(
            session, intern_id=event.intern_id
        )
        await offer_letter.render_and_send(session, intern_id=event.intern_id)


def register(bus: InProcessEventBus) -> None:
    # Onboarding handler creates the NW-ID first; this one issues NDA.
    bus.subscribe(JoiningFormLocked, on_joining_form_locked_issue_nda)
    bus.subscribe(nda_service.NdaSigned, on_nda_signed)
