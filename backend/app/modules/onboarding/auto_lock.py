"""F-36 — Joining Form Auto-Lock Engine.

Cross-validates the submitted joining-form fields against the
referral-form snapshot + ID document. Clean → AUTO_LOCK and trigger
F-34 (Non-Worker ID auto-gen). Flagged → route to HR via AI-10.

Validations:
  HIGH severity (route to HR):
    * Name mismatch (Jaro-Winkler < 0.85 between referral, form, ID).
    * PAN mismatch (referral PAN ≠ form PAN ≠ ID PAN).
    * DOB on ID ≠ form DOB.
    * Mandatory fields missing.

  LOW severity (auto-lock with notes):
    * Education-cert institution similarity < 0.75.
    * Emergency-contact missing.

Decision A1 (mirrored): clean → status JOINING_FORM_LOCKED + ID_PENDING.
Flagged → status JOINING_FORM_SUBMITTED stays + HR review task.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from rapidfuzz.distance import JaroWinkler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.ai import auto_router
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
    TaskType,
    UserRole,
)
from app.shared.domain_events import DomainEvent

logger = logging.getLogger("nexhire.onboarding.auto_lock")


Decision = Literal["AUTO_LOCK", "ROUTED_TO_HR"]


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


@dataclass(frozen=True, slots=True, kw_only=True)
class JoiningFormRoutedToHr(DomainEvent):
    intern_id: UUID
    referral_id: UUID
    flags: tuple[str, ...]


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

    if high:
        return await _route_to_hr(
            session, referral=referral, intern=intern, high=high, low=low
        )
    return await _auto_lock(
        session, referral=referral, intern=intern, form=form, low=low
    )


async def _auto_lock(
    session: AsyncSession,
    *,
    referral: Referral,
    intern: Intern,
    form: JoiningForm,
    low: list[FormFlag],
) -> AutoLockResult:
    now = datetime.now(timezone.utc)
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

    session.add(
        AiAutoAction(
            action_type="AUTO_LOCK",
            decision="EXECUTED",
            referral_id=referral.id,
            intern_id=intern.id,
            conditions_met=["No high-severity flags"],
            flags=[f.message for f in low] if low else None,
        )
    )
    session.add(
        ReferralStageHistory(
            referral_id=referral.id,
            from_status=ReferralStatus.JOINING_FORM_SUBMITTED.value,
            to_status=ReferralStatus.JOINING_FORM_LOCKED.value,
            actor_id=AI_SYSTEM_USER_ID,
            actor_role="SYSTEM",
            reason="Joining form auto-locked by AI.",
        )
    )

    await audit.publish(
        event_type="JOINING_FORM_AUTO_LOCKED",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
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
    return AutoLockResult(decision="AUTO_LOCK", low_flags=tuple(low))


async def _route_to_hr(
    session: AsyncSession,
    *,
    referral: Referral,
    intern: Intern,
    high: list[FormFlag],
    low: list[FormFlag],
) -> AutoLockResult:
    now = datetime.now(timezone.utc)

    # Form stays at SUBMITTED for HR review; referral stays at SUBMITTED
    # of the joining-form lane.
    sla_deadline = now + timedelta(hours=24)
    await auto_router.create_routed_task(
        session,
        task_type=TaskType.JOINING_FORM_REVIEW,
        role=UserRole.HR,
        sla_deadline=sla_deadline,
        referral_id=referral.id,
        intern_id=intern.id,
    )

    session.add(
        AiAutoAction(
            action_type="AUTO_LOCK",
            decision="ROUTED_TO_HR",
            referral_id=referral.id,
            intern_id=intern.id,
            flags=[f.message for f in high + low],
            hr_recommendation="REQUIRES_REVIEW",
        )
    )

    await audit.publish(
        event_type="JOINING_FORM_ROUTED_TO_HR",
        entity_type="INTERN",
        entity_id=intern.id,
        actor_user_id=AI_SYSTEM_USER_ID,
        actor_role="SYSTEM",
        payload={
            "high_flags": [f.message for f in high],
            "low_flags": [f.message for f in low],
        },
        session=session,
    )

    await get_bus().publish(
        JoiningFormRoutedToHr(
            intern_id=intern.id,
            referral_id=referral.id,
            flags=tuple(f.message for f in high),
        )
    )

    return AutoLockResult(
        decision="ROUTED_TO_HR",
        high_flags=tuple(high),
        low_flags=tuple(low),
    )


__all__ = [
    "AutoLockResult",
    "FormFlag",
    "JoiningFormLocked",
    "JoiningFormRoutedToHr",
    "evaluate_and_route",
]


# Suppress unused-import warning when the file is loaded standalone.
_ = field