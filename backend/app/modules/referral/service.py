"""Referral submission orchestrator.

Composes the work that has to happen when a referrer submits the form:

    1. Validate every business rule (RULE-E1..E5, college cap, dates).
    2. Re-run the PAN decision tree server-side (never trust the client).
    3. Encrypt + hash the PAN.
    4. Create the `referrals` row at status=SUBMITTED.
    5. Run AI-3 risk profiling and persist.
    6. Run AI-4 fuzzy duplicate check and persist.
    7. Hand off to the mentor module to create the assignment +
       action tokens. That call advances status to MENTOR_PENDING.
    8. Publish `ReferralSubmitted` and `MentorAssignmentRequested` events.
       Notification handlers (S1.8) react and send emails.
    9. Audit `REFERRAL_SUBMITTED`.

All inside one DB transaction (the FastAPI dependency `get_session`
manages the boundaries — orchestrator never commits).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure import azure_blob
from app.infrastructure.event_bus import get_bus
from app.middleware import audit
from app.modules.ai import service as ai_service
from app.modules.ai.risk_profiler import RiskInput
from app.modules.auth.models import User
from app.modules.mentor import service as mentor_service
from app.modules.referral import college_repository, pan_crypto, validator
from app.modules.referral.models import College, Document, Referral
from app.modules.referral.schemas import (
    ReferralSubmitRequest,
    ReferralSubmitResponse,
)
from app.shared.constants import (
    ALLOWED_UPLOAD_MIME_TYPES,
    DocumentType,
    MAX_FILE_SIZE_BYTES,
    ReferralStatus,
)
from app.shared.domain_events import (
    MentorAssignmentRequested,
    ReferralSubmitted,
    ResumeAnalyzed,
)
from app.shared.exceptions import (
    BusinessRuleError,
    CollegeCapExceededError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.shared.value_objects import (
    MentorAssignmentId,
    ReferralId,
    UserId,
)


logger = logging.getLogger("nexhire.referral.service")


# ────────────────────────────────────────────────────────────────────
# Resume upload + AI parsing (Step 1 of the form).
# ────────────────────────────────────────────────────────────────────
async def upload_resume_and_parse(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    mime_type: str,
    file_name: str,
    referrer_id: UUID,
):  # type: ignore[no-untyped-def]
    """Validate, store, parse. Returns (document, parse_result)."""
    if mime_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise InvalidFileTypeError()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError()

    cfg = get_settings()
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    blob_key = await azure_blob.upload(
        cfg.azure_blob_container_temp,
        file_bytes,
        content_type=mime_type,
        filename=file_name,
    )

    document = Document(
        document_type=DocumentType.RESUME.value,
        azure_blob_container=cfg.azure_blob_container_temp,
        azure_blob_key=blob_key,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=len(file_bytes),
        sha256_hash=sha256,
        uploaded_by=referrer_id,
    )
    session.add(document)
    await session.flush()

    # Persists an `ai_parse_results` row regardless of outcome.
    parse_result = await ai_service.parse_resume_and_persist(
        session,
        referral_id=None,  # no referral row yet — link happens on submit
        file_bytes=file_bytes,
        mime_type=mime_type,
    )

    await get_bus().publish(
        ResumeAnalyzed(
            referral_id=ReferralId(document.id),  # placeholder; replaced on submit
            parse_result_id=document.id,
            succeeded=parse_result.succeeded,
            confidence_min=(
                min(parse_result.confidence_scores.values())
                if parse_result.confidence_scores
                else None
            ),
        )
    )

    return document, parse_result


# ────────────────────────────────────────────────────────────────────
# Realtime PAN check.
# ────────────────────────────────────────────────────────────────────
async def realtime_pan_check(
    session: AsyncSession, *, pan_plain: str
) -> validator.PanCheckResult:
    return await validator.pan_check(session, pan_plain=pan_plain)


# ────────────────────────────────────────────────────────────────────
# Submit.
# ────────────────────────────────────────────────────────────────────
async def submit(
    session: AsyncSession,
    *,
    referrer_id: UUID,
    payload: ReferralSubmitRequest,
    today: date,
    current_year: int,
) -> ReferralSubmitResponse:
    """Run the full submit pipeline."""

    # ── 1. Synchronous validators ──────────────────────────────────
    validator.validate_year_of_study(
        payload.candidate_year_of_study,
        graduation_year=payload.candidate_graduation_year,
        current_year=current_year,
    )
    validator.require_unpaid_consent(payload.unpaid_consent)
    validator.require_inperson_ready(payload.inperson_ready)
    validator.validate_referrer_mentor(
        referrer_id=referrer_id, mentor_id=payload.mentor_id
    )
    validator.validate_dates(
        start=payload.internship_start_date,
        end=payload.internship_end_date,
        today=today,
    )

    # ── 2. College + cap (RULE-E2). ────────────────────────────────
    college = await college_repository.get_by_id(session, payload.college_id)
    if college is None:
        raise BusinessRuleError(
            user_message="The selected college could not be found.",
            details={"college_id": str(payload.college_id)},
        )
    cap = await validator.check_college_cap(
        session, referrer_id=referrer_id, college_id=college.id
    )
    if not cap.can_submit:
        raise CollegeCapExceededError(college=college.canonical_name)

    # ── 3. Mentor capacity (RULE-M-CAP). ───────────────────────────
    await validator.validate_mentor_capacity(session, mentor_id=payload.mentor_id)

    # ── 4. PAN decision tree (F-40 steps 1–2). Hard guards raise. ──
    pan_result = await validator.pan_check(
        session, pan_plain=payload.candidate_pan
    )
    validator.raise_if_blocked(pan_result)

    # ── 5. Persist the referral row at SUBMITTED. ─────────────────
    referral = Referral(
        referrer_id=referrer_id,
        mentor_id=payload.mentor_id,
        candidate_name=payload.candidate_name.strip(),
        candidate_email=payload.candidate_email.lower(),
        candidate_phone=payload.candidate_phone,
        college_id=college.id,
        candidate_year_of_study=payload.candidate_year_of_study,
        candidate_graduation_year=payload.candidate_graduation_year,
        candidate_pan_hash=pan_crypto.hash_for_lookup(payload.candidate_pan),
        candidate_pan_encrypted=pan_crypto.encrypt_for_display(payload.candidate_pan),
        candidate_pan_masked=pan_crypto.mask(payload.candidate_pan),
        project_title=payload.project_title,
        project_overview=payload.project_overview,
        joining_location=payload.joining_location,
        internship_start_date=payload.internship_start_date,
        internship_end_date=payload.internship_end_date,
        relationship_declaration=payload.relationship_declaration,
        relationship_declaration_detail=payload.relationship_declaration_detail,
        unpaid_consent=payload.unpaid_consent,
        inperson_ready=payload.inperson_ready,
        status=ReferralStatus.SUBMITTED.value,
        current_stage=ReferralStatus.SUBMITTED.value,
        resume_document_id=payload.resume_document_id,
    )
    session.add(referral)
    await session.flush()

    # ── 6. AI-3 risk profile + AI-4 fuzzy duplicate check. ────────
    risk_input = RiskInput(
        candidate_name=referral.candidate_name,
        college_name=college.canonical_name,
        college_state=college.location_state,
        joining_location=referral.joining_location,
        joining_state=None,
        start_date=referral.internship_start_date,
        end_date=referral.internship_end_date,
    )
    risk_result = await ai_service.assess_risk_and_persist(
        session, referral_id=referral.id, form=risk_input
    )

    fuzzy_result = await ai_service.fuzzy_duplicate_check_and_persist(
        session,
        referral_id=referral.id,
        candidate_name=referral.candidate_name,
        candidate_email=referral.candidate_email,
        candidate_phone=referral.candidate_phone,
    )
    duplicate_warning: str | None = None
    if fuzzy_result.recommendation == "SOFT_BLOCK":
        duplicate_warning = (
            f"A possible duplicate ({int(fuzzy_result.similarity_score * 100)}% match) "
            f"was found. HR will verify during review."
        )
    elif fuzzy_result.recommendation == "WARN":
        duplicate_warning = "A possible match was found and will be verified by HR."

    # ── 7. Mentor assignment + tokens. Advances status to MENTOR_PENDING. ──
    assignment, accept_token, reject_token = await mentor_service.request_assignment(
        session,
        referral_id=referral.id,
        mentor_id=payload.mentor_id,
        referrer_id=referrer_id,
    )

    # ── 8. Audit + domain events. ─────────────────────────────────
    await audit.publish(
        event_type="REFERRAL_SUBMITTED",
        entity_type="REFERRAL",
        entity_id=referral.id,
        actor_user_id=referrer_id,
        actor_role="REFERRER",
        payload={
            "candidate_email": referral.candidate_email,
            "college_id": str(college.id),
            "college_name": college.canonical_name,
            "mentor_id": str(payload.mentor_id),
            "pan_masked": referral.candidate_pan_masked,
            "risk_score": risk_result.risk_score,
            "risk_classification": risk_result.classification,
            "duplicate_recommendation": fuzzy_result.recommendation,
        },
        session=session,
    )

    bus = get_bus()
    await bus.publish(
        ReferralSubmitted(
            referral_id=ReferralId(referral.id),
            referrer_id=UserId(referrer_id),
            candidate_email=referral.candidate_email,
            candidate_name=referral.candidate_name,
            selected_mentor_id=UserId(payload.mentor_id),
            college_id=college.id,
            pan_masked=referral.candidate_pan_masked,
        )
    )
    await bus.publish(
        MentorAssignmentRequested(
            referral_id=ReferralId(referral.id),
            mentor_id=UserId(payload.mentor_id),
            assignment_id=MentorAssignmentId(assignment.id),
            attempt_number=assignment.attempt_number,
            accept_token=accept_token.raw_token,
            reject_token=reject_token.raw_token,
        )
    )

    return ReferralSubmitResponse(
        referral_id=cast(UUID, referral.id),
        status=referral.status,
        risk_score=risk_result.risk_score,
        risk_classification=risk_result.classification,
        duplicate_warning=duplicate_warning,
    )


# ────────────────────────────────────────────────────────────────────
# Mentor picker (basic; AI-2 lands in S2).
# ────────────────────────────────────────────────────────────────────
async def list_eligible_mentors(
    session: AsyncSession,
    *,
    threshold: int,
    exclude_user_id: UUID | None = None,
):  # type: ignore[no-untyped-def]
    """Returns (User, active_mentee_count) pairs where can_mentor=true
    and the user is active. Excludes the requesting referrer (RULE-E3
    UI hint; the validator still hard-blocks at submit).
    """
    from sqlalchemy import func, text

    base = (
        select(
            User,
            func.coalesce(
                func.count(text("ma.id")).filter(text("ma.status = 'ACCEPTED'")),
                0,
            ).label("active_mentees"),
        )
        .join(
            text(
                "mentor_assignments AS ma "
                "ON ma.mentor_id = users.id "
                "AND ma.status = 'ACCEPTED'"
            ),
            isouter=True,
        )
        .where(User.can_mentor.is_(True), User.is_active.is_(True))
        .group_by(User.id)
        .order_by(User.full_name.asc())
    )
    if exclude_user_id is not None:
        base = base.where(User.id != exclude_user_id)

    rows = (await session.execute(base)).all()
    return [(user, int(active)) for user, active in rows]


__all__ = [
    "list_eligible_mentors",
    "realtime_pan_check",
    "submit",
    "upload_resume_and_parse",
]
