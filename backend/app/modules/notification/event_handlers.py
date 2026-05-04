"""Notification event handlers.

Subscribed at app startup (see `app.wiring`). Each handler:
  1. Receives a domain event.
  2. Opens its own DB session (the originating transaction has long
     since committed by the time the bus invokes us).
  3. Loads enough context for the template.
  4. Calls `notification.service.send_template(...)`.
  5. Lets `send_template` decide whether to mark the row SENT or FAILED.

Handler failures are isolated by the bus and reach the outbox table;
no exception escapes the handler.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.auth.models import User
from app.modules.notification import service as notification_service
from app.modules.referral import repository as referral_repo
from app.modules.referral.models import College
from app.shared.constants import NotificationTemplate
from app.shared.domain_events import (
    MentorAssignmentRequested,
    ReferralSubmitted,
)

logger = logging.getLogger("nexhire.notification.handlers")


# ────────────────────────────────────────────────────────────────────
# ReferralSubmitted → email the referrer.
# ────────────────────────────────────────────────────────────────────
async def on_referral_submitted(event: ReferralSubmitted) -> None:
    factory = get_sessionmaker()
    cfg = get_settings()
    portal_url = cfg.azure_ad_redirect_uri.rsplit("/auth/callback", 1)[0]

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            logger.warning(
                "nexhire.notification.referral_missing",
                extra={"referral_id": str(event.referral_id)},
            )
            return

        referrer = (
            await session.execute(select(User).where(User.id == event.referrer_id))
        ).scalar_one()
        mentor = (
            await session.execute(
                select(User).where(User.id == event.selected_mentor_id)
            )
        ).scalar_one()
        college = (
            await session.execute(
                select(College).where(College.id == referral.college_id)
            )
        ).scalar_one()

        await notification_service.send_template(
            session,
            template_id=NotificationTemplate.REFERRAL_CONFIRMATION.value,
            recipient=referrer.email,
            referral_id=referral.id,
            context={
                "referrer_name": referrer.full_name,
                "candidate_name": event.candidate_name,
                "mentor_name": mentor.full_name,
                "college_name": college.canonical_name,
                "project_title": referral.project_title or "",
                "referral_id": str(referral.id),
                "portal_url": portal_url,
            },
        )


# ────────────────────────────────────────────────────────────────────
# MentorAssignmentRequested → email the mentor with action-token URLs.
# ────────────────────────────────────────────────────────────────────
async def on_mentor_assignment_requested(
    event: MentorAssignmentRequested,
) -> None:
    factory = get_sessionmaker()
    cfg = get_settings()
    base_url = cfg.azure_ad_redirect_uri.rsplit("/auth/callback", 1)[0]

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            logger.warning(
                "nexhire.notification.referral_missing",
                extra={"referral_id": str(event.referral_id)},
            )
            return

        mentor = (
            await session.execute(select(User).where(User.id == event.mentor_id))
        ).scalar_one()
        referrer = (
            await session.execute(
                select(User).where(User.id == referral.referrer_id)
            )
        ).scalar_one()
        college = (
            await session.execute(
                select(College).where(College.id == referral.college_id)
            )
        ).scalar_one()

        # The active mentee count we surface to the mentor for context
        # — same query the picker uses, so the mentor sees a familiar
        # number.
        from app.modules.referral import service as referral_service
        from app.modules.referral.models import MentorThresholdConfig

        threshold_row = (
            await session.execute(
                select(MentorThresholdConfig).where(
                    MentorThresholdConfig.is_current.is_(True)
                )
            )
        ).scalar_one()
        rows = await referral_service.list_eligible_mentors(
            session, threshold=threshold_row.max_mentees
        )
        active_mentees = next(
            (count for user, count in rows if user.id == mentor.id),
            0,
        )

        accept_url = f"{base_url}/action/mentor?token={event.accept_token}&action=ACCEPT"
        reject_url = f"{base_url}/action/mentor?token={event.reject_token}&action=REJECT"

        await notification_service.send_template(
            session,
            template_id=NotificationTemplate.MENTOR_ASSIGNMENT.value,
            recipient=mentor.email,
            referral_id=referral.id,
            context={
                "mentor_name": mentor.full_name,
                "referrer_name": referrer.full_name,
                "candidate_name": referral.candidate_name,
                "college_name": college.canonical_name,
                "project_title": referral.project_title or "",
                "candidate_summary": referral.project_overview or "",
                "start_date": (
                    referral.internship_start_date.isoformat()
                    if referral.internship_start_date
                    else "TBD"
                ),
                "end_date": (
                    referral.internship_end_date.isoformat()
                    if referral.internship_end_date
                    else "TBD"
                ),
                "accept_url": accept_url,
                "reject_url": reject_url,
                "mentor_active_mentees": f"{active_mentees}/{threshold_row.max_mentees}",
            },
        )


# ────────────────────────────────────────────────────────────────────
# Subscription registration. Called from app.wiring on startup so the
# bus (a singleton) is wired identically every boot. Tests get a fresh
# bus via reset_bus_for_tests + manually re-call this.
# ────────────────────────────────────────────────────────────────────
def register(bus: InProcessEventBus) -> None:
    bus.subscribe(ReferralSubmitted, on_referral_submitted)
    bus.subscribe(MentorAssignmentRequested, on_mentor_assignment_requested)
