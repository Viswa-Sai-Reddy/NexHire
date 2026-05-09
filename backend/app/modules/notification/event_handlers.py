"""Notification event handlers.

Subscribed at app startup (see `app.wiring`). Each handler:
  1. Receives a domain event.
  2. Opens its own DB session.
  3. Loads enough context for the template (with a short retry — the
     producer's request transaction may not have committed yet when the
     bus dispatches us; see `_load_referral_with_retry`).
  4. Calls `notification.service.send_template(...)`.
  5. Lets `send_template` decide whether to mark the row SENT or FAILED.

Handler failures are isolated by the bus and reach the outbox table;
no exception escapes the handler.
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select, text as sa_text

from app.config import get_settings
from app.infrastructure.database import get_sessionmaker
from app.infrastructure.event_bus import InProcessEventBus
from app.modules.auth.models import User
from app.modules.lifecycle import service as lifecycle_service
from app.modules.nda import service as nda_service
from app.modules.notification import service as notification_service
from app.modules.onboarding.models import Intern
from app.modules.referral import repository as referral_repo
from app.modules.referral.models import College
from app.shared.constants import NotificationTemplate
from app.shared.domain_events import (
    CandidateMagicLinkIssued,
    MentorAssignmentRequested,
    ReferralSubmitted,
)

logger = logging.getLogger("nexhire.notification.handlers")


async def _wait_for_referral_visible(
    referral_id: UUID,
    *,
    attempts: int = 4,
    delay_seconds: float = 0.25,
) -> bool:
    """Poll for a referral row to become visible.

    The bus invokes handlers from inside the producer's request, so the
    producer's transaction may not have committed yet by the time the
    handler runs. Without polling, the handler races the commit and
    reads NULL. Uses a fresh session per attempt so each read sees the
    latest committed snapshot regardless of producer-transaction timing.

    Returns True if the row became visible, False if the budget is
    exhausted (in which case the row almost certainly doesn't exist —
    the producer rolled back).
    """
    factory = get_sessionmaker()
    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(delay_seconds)
        async with factory() as s, s.begin():
            referral = await referral_repo.get(s, referral_id)
            if referral is not None:
                return True
    return False


# ────────────────────────────────────────────────────────────────────
# ReferralSubmitted → email the referrer.
# ────────────────────────────────────────────────────────────────────
async def on_referral_submitted(event: ReferralSubmitted) -> None:
    factory = get_sessionmaker()
    cfg = get_settings()
    portal_url = cfg.frontend_base_url

    if not await _wait_for_referral_visible(event.referral_id):
        logger.warning(
            "nexhire.notification.referral_missing",
            extra={"referral_id": str(event.referral_id)},
        )
        return

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            # Defensive: row vanished between visibility check and now.
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
    base_url = cfg.frontend_base_url

    if not await _wait_for_referral_visible(event.referral_id):
        logger.warning(
            "nexhire.notification.referral_missing",
            extra={"referral_id": str(event.referral_id)},
        )
        return

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
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
# CandidateMagicLinkIssued → email the candidate the joining-form link.
# ────────────────────────────────────────────────────────────────────
async def on_candidate_magic_link_issued(
    event: CandidateMagicLinkIssued,
) -> None:
    logger.info(
        f"on_candidate_magic_link_issued: referral_id={event.referral_id} "
        f"candidate_email={event.candidate_email}"
    )
    factory = get_sessionmaker()
    cfg = get_settings()
    base_url = cfg.frontend_base_url

    if not await _wait_for_referral_visible(event.referral_id):
        logger.warning(
            f"on_candidate_magic_link_issued: referral {event.referral_id} not visible"
        )
        return

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            logger.warning(
                f"on_candidate_magic_link_issued: referral {event.referral_id} "
                "vanished after visibility check"
            )
            return

        # Self-heal: ensure the template row exists even if the migration
        # adding NOTIF_022 hasn't been applied yet. Idempotent upsert.
        await session.execute(
            sa_text(
                """
                INSERT INTO notification_templates (template_id, subject)
                VALUES (:tid, :subj)
                ON CONFLICT (template_id) DO NOTHING
                """
            ).bindparams(
                tid=NotificationTemplate.JOINING_FORM_INVITE.value,
                subj="Action required: complete your joining form",
            )
        )

        magic_url = f"{base_url}/candidate/access?token={event.raw_token}"

        try:
            notification = await notification_service.send_template(
                session,
                template_id=NotificationTemplate.JOINING_FORM_INVITE.value,
                recipient=event.candidate_email,
                referral_id=referral.id,
                context={
                    "candidate_name": event.candidate_name,
                    "project_title": referral.project_title or "",
                    "joining_location": referral.joining_location or "",
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
                    "magic_url": magic_url,
                    "expires_at": event.expires_at.isoformat(),
                },
            )
        except Exception as exc:
            logger.exception(
                f"on_candidate_magic_link_issued: send_template raised {exc!r}"
            )
            raise
        logger.info(
            f"on_candidate_magic_link_issued: notification.status="
            f"{notification.status} last_error={notification.last_error!r}"
        )


# ────────────────────────────────────────────────────────────────────
# NdaSigned → email the candidate their Non-Worker ID + welcome.
# ────────────────────────────────────────────────────────────────────
async def _wait_for_non_worker_id(
    intern_id: UUID,
    *,
    attempts: int = 6,
    delay_seconds: float = 0.5,
) -> str | None:
    """Poll for `intern.non_worker_id` to be populated.

    Two `JoiningFormLocked` handlers race: one generates the NW-ID,
    the other issues the NDA. If the candidate signs the NDA quickly
    (or the NW-ID handler is slow), `NdaSigned` can fire before the
    NW-ID is committed. Each attempt opens a fresh session so we read
    the latest committed snapshot.
    """
    factory = get_sessionmaker()
    for attempt in range(attempts):
        if attempt > 0:
            await asyncio.sleep(delay_seconds)
        async with factory() as s, s.begin():
            row = (
                await s.execute(
                    select(Intern.non_worker_id).where(Intern.id == intern_id)
                )
            ).scalar_one_or_none()
            if row:
                return row
    return None


async def on_nda_signed_send_congratulations(
    event: nda_service.NdaSigned,
) -> None:
    logger.info(
        f"on_nda_signed_send_congratulations: intern_id={event.intern_id} "
        f"referral_id={event.referral_id}"
    )
    factory = get_sessionmaker()
    cfg = get_settings()
    portal_url = f"{cfg.frontend_base_url}/candidate/login"

    if not await _wait_for_referral_visible(event.referral_id):
        logger.warning(
            f"on_nda_signed_send_congratulations: referral {event.referral_id} "
            "not visible"
        )
        return

    # Poll for NW-ID to land before composing the email — avoids shipping
    # "(pending)" when the NW-ID generator is just a moment behind the
    # NDA-signed handler.
    nw_id = await _wait_for_non_worker_id(event.intern_id)
    if nw_id is None:
        logger.warning(
            f"on_nda_signed_send_congratulations: NW-ID still missing after "
            f"polling for intern {event.intern_id}; sending with placeholder"
        )

    async with factory() as session, session.begin():
        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            return

        intern = (
            await session.execute(select(Intern).where(Intern.id == event.intern_id))
        ).scalar_one_or_none()
        if intern is None:
            logger.warning(
                f"on_nda_signed_send_congratulations: intern {event.intern_id} missing"
            )
            return

        candidate_user = (
            await session.execute(select(User).where(User.id == intern.user_id))
        ).scalar_one()

        try:
            notification = await notification_service.send_template(
                session,
                template_id=NotificationTemplate.CONGRATULATIONS_TO_CANDIDATE.value,
                recipient=candidate_user.email,
                referral_id=referral.id,
                context={
                    "candidate_name": candidate_user.full_name,
                    "non_worker_id": (
                        nw_id or intern.non_worker_id or "(pending)"
                    ),
                    "project_title": referral.project_title or "",
                    "joining_location": referral.joining_location or "",
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
                    "portal_url": portal_url,
                },
            )
        except Exception as exc:
            logger.exception(
                f"on_nda_signed_send_congratulations: send_template raised {exc!r}"
            )
            raise
        logger.info(
            f"on_nda_signed_send_congratulations: notification.status="
            f"{notification.status} last_error={notification.last_error!r}"
        )


# ────────────────────────────────────────────────────────────────────
# InternshipClosed → email the candidate the certificate-delivery note.
# ────────────────────────────────────────────────────────────────────
async def on_internship_closed_send_certificate(
    event: lifecycle_service.InternshipClosed,
) -> None:
    logger.info(
        f"on_internship_closed_send_certificate: intern_id={event.intern_id} "
        f"referral_id={event.referral_id}"
    )
    factory = get_sessionmaker()
    cfg = get_settings()
    portal_url = f"{cfg.frontend_base_url}/candidate/login"

    if not await _wait_for_referral_visible(event.referral_id):
        logger.warning(
            f"on_internship_closed_send_certificate: referral {event.referral_id} "
            "not visible"
        )
        return

    async with factory() as session, session.begin():
        # Self-heal the template row in case migration not applied.
        await session.execute(
            sa_text(
                """
                INSERT INTO notification_templates (template_id, subject)
                VALUES (:tid, :subj)
                ON CONFLICT (template_id) DO NOTHING
                """
            ).bindparams(
                tid=NotificationTemplate.CERTIFICATE_DELIVERY.value,
                subj="Your internship is complete — download your certificate",
            )
        )

        referral = await referral_repo.get(session, event.referral_id)
        if referral is None:
            return

        intern = (
            await session.execute(select(Intern).where(Intern.id == event.intern_id))
        ).scalar_one_or_none()
        if intern is None:
            logger.warning(
                f"on_internship_closed_send_certificate: intern {event.intern_id} missing"
            )
            return

        candidate_user = (
            await session.execute(select(User).where(User.id == intern.user_id))
        ).scalar_one()

        try:
            notification = await notification_service.send_template(
                session,
                template_id=NotificationTemplate.CERTIFICATE_DELIVERY.value,
                recipient=candidate_user.email,
                referral_id=referral.id,
                context={
                    "candidate_name": candidate_user.full_name,
                    "non_worker_id": intern.non_worker_id or "(n/a)",
                    "project_title": referral.project_title or "",
                    "start_date": (
                        referral.internship_start_date.isoformat()
                        if referral.internship_start_date
                        else "TBD"
                    ),
                    "end_date": (
                        intern.actual_end_date.isoformat()
                        if intern.actual_end_date
                        else (
                            referral.internship_end_date.isoformat()
                            if referral.internship_end_date
                            else "TBD"
                        )
                    ),
                    "portal_url": portal_url,
                },
            )
        except Exception as exc:
            logger.exception(
                f"on_internship_closed_send_certificate: send_template raised {exc!r}"
            )
            raise
        logger.info(
            f"on_internship_closed_send_certificate: notification.status="
            f"{notification.status} last_error={notification.last_error!r}"
        )


# ────────────────────────────────────────────────────────────────────
# Subscription registration. Called from app.wiring on startup so the
# bus (a singleton) is wired identically every boot. Tests get a fresh
# bus via reset_bus_for_tests + manually re-call this.
# ────────────────────────────────────────────────────────────────────
def register(bus: InProcessEventBus) -> None:
    bus.subscribe(ReferralSubmitted, on_referral_submitted)
    bus.subscribe(MentorAssignmentRequested, on_mentor_assignment_requested)
    bus.subscribe(CandidateMagicLinkIssued, on_candidate_magic_link_issued)
    bus.subscribe(nda_service.NdaSigned, on_nda_signed_send_congratulations)
    bus.subscribe(
        lifecycle_service.InternshipClosed, on_internship_closed_send_certificate
    )
    logger.info(
        "notification handlers registered: ReferralSubmitted, "
        "MentorAssignmentRequested, CandidateMagicLinkIssued, NdaSigned, "
        "InternshipClosed"
    )
