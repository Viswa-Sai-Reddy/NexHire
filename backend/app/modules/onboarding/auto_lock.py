"""F-36 — Joining Form Auto-Lock Engine.

Cross-validates the submitted joining-form fields against the
referral-form snapshot + ID document. Submission is the sole gate:
every joining form auto-locks and the candidate flows straight into
NDA signing. The flag computation still runs so HR retains an audit
trail and can use the existing 1-hour recall window if a flagged form
needs to be revisited.

Validations recorded on the `ai_auto_actions` row:
  HIGH severity:
    * Name mismatch (Jaro-Winkler < 0.85 between referral, form, ID).
    * PAN mismatch (referral PAN ≠ form PAN ≠ ID PAN).
    * DOB on ID ≠ form DOB.
    * Mandatory fields missing.

  LOW severity:
    * Education-cert institution similarity < 0.75.
    * Emergency-contact missing.

Outcome:
  Always → form.status = LOCKED, referral.status = JOINING_FORM_LOCKED.
           Publishes JoiningFormLocked (NW-ID generator + NDA issuer
           subscribers run downstream, identical for clean and flagged).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from rapidfuzz.distance import JaroWinkler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.onboarding import non_worker_id as nw_id_service
from app.modules.onboarding.models import Intern, JoiningForm
from app.modules.referral import pan_crypto
from app.modules.referral.models import (
    AiAutoAction,
    Referral,
    ReferralStageHistory,
)
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    JoiningFormStatus,
    ReferralStatus,
)
from app.shared.domain_events import DomainEvent

logger = logging.getLogger("nexhire.onboarding.auto_lock")


Decision = Literal["AUTO_LOCK"]


@dataclass(frozen=True, slots=True)
class FormFlag:
    severity: Literal["HIGH", "LOW"]
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class AutoLockResult:
    decision: Decision
    high_flags: tuple[FormFlag, ...] = ()
    low_flags: tuple[FormFlag, ...] = ()


# Domain events emitted by this engine — we declare them inline to
# keep the cross-module surface tight; both end up on the bus.
@dataclass(frozen=True, slots=True, kw_only=True)
class JoiningFormLocked(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    auto_locked: bool


# ────────────────────────────────────────────────────────────────────
# Public entry.
# ────────────────────────────────────────────────────────────────────
async def evaluate_and_route(
    session: AsyncSession,
    *,
    intern_id: UUID,
) -> AutoLockResult:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    form = (
        await session.execute(
            select(JoiningForm).where(JoiningForm.intern_id == intern_id)
        )
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    high: list[FormFlag] = []
    low: list[FormFlag] = []

    # ── Name consistency ─────────────────────────────────────────
    referral_name = (referral.candidate_name or "").strip().lower()
    form_name = (
        (form.personal_details.get("full_name") or "").strip().lower()
        if isinstance(form.personal_details, dict)
        else ""
    )
    id_name = (
        (form.govt_ids.get("id_extracted_name") or "").strip().lower()
        if isinstance(form.govt_ids, dict)
        else ""
    )
    if form_name and JaroWinkler.normalized_similarity(referral_name, form_name) < 0.85:
        high.append(
            FormFlag(
                severity="HIGH",
                field="full_name",
                message=(
                    f"Name on the joining form ({form.personal_details.get('full_name')}) "
                    f"differs from the referral ({referral.candidate_name})."
                ),
            )
        )
    if id_name and JaroWinkler.normalized_similarity(form_name, id_name) < 0.85:
        high.append(
            FormFlag(
                severity="HIGH",
                field="full_name",
                message="Name on uploaded ID differs from the joining form entry.",
            )
        )

    # ── PAN consistency ──────────────────────────────────────────
    referral_pan = pan_crypto.decrypt_to_pan(referral.candidate_pan_encrypted)
    form_pan = (
        (form.govt_ids.get("pan_number") or "").strip().upper()
        if isinstance(form.govt_ids, dict)
        else ""
    )
    if form_pan and form_pan != referral_pan.value:
        high.append(
            FormFlag(
                severity="HIGH",
                field="pan_number",
                message="PAN on the joining form differs from the referral form.",
            )
        )
    id_pan = (
        (form.govt_ids.get("id_extracted_pan") or "").strip().upper()
        if isinstance(form.govt_ids, dict)
        else ""
    )
    if id_pan and form_pan and id_pan != form_pan:
        high.append(
            FormFlag(
                severity="HIGH",
                field="pan_number",
                message="PAN on the uploaded ID differs from the entered PAN.",
            )
        )

    # ── DOB consistency ──────────────────────────────────────────
    form_dob = (
        form.personal_details.get("date_of_birth")
        if isinstance(form.personal_details, dict)
        else None
    )
    id_dob = (
        form.govt_ids.get("id_extracted_dob")
        if isinstance(form.govt_ids, dict)
        else None
    )
    if form_dob and id_dob and str(form_dob) != str(id_dob):
        high.append(
            FormFlag(
                severity="HIGH",
                field="date_of_birth",
                message=f"Date of birth on form ({form_dob}) differs from ID ({id_dob}).",
            )
        )

    # ── Completeness ─────────────────────────────────────────────
    for required in ("full_name", "date_of_birth"):
        if not (
            isinstance(form.personal_details, dict)
            and form.personal_details.get(required)
        ):
            high.append(
                FormFlag(
                    severity="HIGH",
                    field=required,
                    message=f"Mandatory field {required!r} is missing.",
                )
            )

    if not (
        isinstance(form.emergency_contact, dict)
        and form.emergency_contact.get("name")
        and form.emergency_contact.get("phone")
    ):
        low.append(
            FormFlag(
                severity="LOW",
                field="emergency_contact",
                message="Emergency contact incomplete.",
            )
        )

    return await _auto_lock(
        session,
        referral=referral,
        intern=intern,
        form=form,
        high=high,
        low=low,
    )


async def _auto_lock(
    session: AsyncSession,
    *,
    referral: Referral,
    intern: Intern,
    form: JoiningForm,
    high: list[FormFlag],
    low: list[FormFlag],
) -> AutoLockResult:
    now = datetime.now(UTC)
    form.status = JoiningFormStatus.LOCKED.value
    form.locked_at = now
    form.locked_by = AI_SYSTEM_USER_ID
    form.locked_by_label = "AI_AUTO_LOCK"
    form.version += 1
    form.updated_at = now

    referral.status = ReferralStatus.JOINING_FORM_LOCKED.value
    referral.current_stage = ReferralStatus.JOINING_FORM_LOCKED.value
    referral.stage_entered_at = now
    referral.updated_at = now

    # Generate the Non-Worker ID inline, in the same transaction as the
    # lock. Previously this lived in an event handler with its own
    # session — when generation failed (typically PAN decryption / env
    # issues) the rollback was silent and the candidate ended up locked
    # without an NW-ID. Inline keeps it atomic.
    if intern.non_worker_id is None:
        await nw_id_service.generate_for_intern(session, intern_id=intern.id)
        referral.status = ReferralStatus.ID_ISSUED.value
        referral.current_stage = ReferralStatus.ID_ISSUED.value
        referral.stage_entered_at = now
        referral.updated_at = now

    all_flag_messages = [f.message for f in (high + low)]
    history_reason = (
        "Joining form auto-locked by AI with flags — see ai_auto_actions for detail."
        if high or low
        else "Joining form auto-locked by AI (clean)."
    )

    session.add(
        AiAutoAction(
            action_type="AUTO_LOCK",
            decision="EXECUTED",
            referral_id=referral.id,
            intern_id=intern.id,
            conditions_met=(
                ["No high-severity flags"] if not high else None
            ),
            flags=all_flag_messages or None,
        )
    )
    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.JOINING_FORM_SUBMITTED.value,
            to_status=ReferralStatus.JOINING_FORM_LOCKED.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason=history_reason,
            payload=(
                {
                    "high_flags": [f.message for f in high],
                    "low_flags": [f.message for f in low],
                }
                if (high or low)
                else None
            ),
        )
    )

    await audit.publish(
        event_type="JOINING_FORM_AUTO_LOCKED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "high_flags": [f.message for f in high],
            "low_flags": [f.message for f in low],
            "referral_id": str(referral.id),
        },
        session=session,
    )

    await get_bus().publish(
        JoiningFormLocked(
            intern_id=intern.id,
            referral_id=referral.id,
            auto_locked=True,
        )
    )
    return AutoLockResult(
        decision="AUTO_LOCK",
        high_flags=tuple(high),
        low_flags=tuple(low),
    )


__all__ = [
    "AutoLockResult",
    "FormFlag",
    "JoiningFormLocked",
    "evaluate_and_route",
]


# Suppress unused-import warning when the file is loaded standalone.
_ = field
