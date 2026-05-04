"""F-34 — Non-Worker ID auto-generation.

Format: `NW-{PAN}-{YEAR}` with a `-N` sequence suffix on collisions.

Pure-deterministic: same PAN + same joining year always produce the
same ID. Triggered by the `JoiningFormLocked` event (S3.7).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware import audit
from app.modules.onboarding.models import Intern
from app.modules.referral import pan_crypto
from app.modules.referral.models import Referral
from app.shared.constants import AI_SYSTEM_USER_ID
from app.shared.exceptions import (
    BusinessRuleError,
    NonWorkerIdAlreadyIssuedError,
)

logger = logging.getLogger("nexhire.onboarding.nw_id")

ID_PREFIX = "NW"


async def generate_for_intern(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> str:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    if intern.non_worker_id is not None:
        raise NonWorkerIdAlreadyIssuedError()

    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    plain_pan = pan_crypto.decrypt_to_pan(referral.candidate_pan_encrypted)
    joining_year = (
        intern.actual_start_date.year
        if intern.actual_start_date
        else (
            referral.internship_start_date.year
            if referral.internship_start_date
            else _current_year()
        )
    )
    base_id = f"{ID_PREFIX}-{plain_pan.value}-{joining_year}"

    # Collision handling: a candidate doing two stints in the same year
    # gets `-2`, `-3`, …
    candidate_id = base_id
    sequence = 1
    while True:
        existing = (
            await session.execute(
                select(Intern.id).where(Intern.non_worker_id == candidate_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            break
        sequence += 1
        candidate_id = f"{base_id}-{sequence}"
        if sequence > 100:
            raise BusinessRuleError(
                user_message="Could not allocate a Non-Worker ID after 100 attempts."
            )

    intern.non_worker_id = candidate_id

    await audit.publish(
        event_type="NON_WORKER_ID_AUTO_GENERATED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "non_worker_id": candidate_id,
            "pan_masked": referral.candidate_pan_masked,
            "joining_year": joining_year,
            "generated_from": "PAN_NUMBER",
        },
        session=session,
    )
    logger.info(
        "nexhire.onboarding.nw_id_generated",
        extra={"intern_id": str(intern.id), "non_worker_id": candidate_id},
    )
    return candidate_id


def _current_year() -> int:
    from datetime import date

    return date.today().year


__all__ = ["ID_PREFIX", "generate_for_intern"]
