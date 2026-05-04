"""Referral HTTP surface — /referrals/*.

Endpoints (S1):
  POST /referrals/upload-resume   — multipart upload; returns AI-1 prefill
  POST /referrals/check-pan       — realtime PAN decision tree (F-40)
  POST /referrals                 — submit a complete form
  GET  /referrals/me              — referrer's own referrals
  GET  /referrals/{id}            — single referral detail (referrer
                                    or HR/PO; authorization checked)
  GET  /referrals/college-cap     — used count for (referrer, college)
"""
from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.auth.rbac import Permission, assert_permission, require
from app.modules.referral import college_repository, repository, service, validator
from app.modules.referral.schemas import (
    CollegeCapStatus,
    PanCheckRequest,
    PanCheckResponse,
    ReferralDetail,
    ReferralSubmitRequest,
    ReferralSubmitResponse,
    ReferralSummary,
    ResumePrefillResponse,
)
from app.shared.constants import UserRole
from app.shared.exceptions import (
    BusinessRuleError,
    InsufficientPermissionsError,
)


logger = logging.getLogger("nexhire.router.referral")

router = APIRouter(prefix="/referrals", tags=["referrals"])


# ────────────────────────────────────────────────────────────────────
# POST /referrals/upload-resume
# ────────────────────────────────────────────────────────────────────
@router.post(
    "/upload-resume",
    response_model=ResumePrefillResponse,
    dependencies=[Depends(rate_limit("ai")), Depends(require(Permission.SUBMIT_REFERRAL))],
    summary="Upload a resume and receive AI-prefilled candidate fields.",
)
async def upload_resume(
    principal: CurrentUser,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ResumePrefillResponse:
    raw = await file.read()
    document, parse_result = await service.upload_resume_and_parse(
        session,
        file_bytes=raw,
        mime_type=file.content_type or "application/octet-stream",
        file_name=file.filename or "resume",
        referrer_id=principal.user_id,
    )

    response = ResumePrefillResponse(
        document_id=document.id,
        succeeded=parse_result.succeeded,
        user_message=parse_result.user_message,
        degradation_reason=parse_result.degradation_reason,
    )
    if parse_result.data:
        d = parse_result.data
        response = response.model_copy(
            update={
                "candidate_name": _value_str(d.candidate_name.value),
                "candidate_name_confidence": d.candidate_name.confidence,
                "candidate_email": _value_str(d.email.value),
                "candidate_email_confidence": d.email.confidence,
                "candidate_phone": _value_str(d.phone.value),
                "candidate_phone_confidence": d.phone.confidence,
                "candidate_year_of_study": _value_int(d.year_of_study.value),
                "candidate_year_of_study_confidence": d.year_of_study.confidence,
                "college_name": _value_str(d.college.value),
                "college_name_confidence": d.college.confidence,
                "candidate_graduation_year": _value_int(d.graduation_year.value),
                "candidate_graduation_year_confidence": d.graduation_year.confidence,
                "skills": d.skills,
                "suggested_project_tracks": d.suggested_project_tracks,
                "red_flags": d.red_flags,
                "recommended_mentor_questions": d.recommended_mentor_questions,
                "internship_readiness_score": d.internship_readiness_score,
            }
        )
    return response


def _value_str(v) -> str | None:  # type: ignore[no-untyped-def]
    if v is None or v == "":
        return None
    return str(v)


def _value_int(v) -> int | None:  # type: ignore[no-untyped-def]
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ────────────────────────────────────────────────────────────────────
# POST /referrals/check-pan
# ────────────────────────────────────────────────────────────────────
@router.post(
    "/check-pan",
    response_model=PanCheckResponse,
    dependencies=[Depends(rate_limit("ai")), Depends(require(Permission.SUBMIT_REFERRAL))],
    summary="Realtime PAN decision tree (F-40 steps 1–2).",
)
async def check_pan(
    body: PanCheckRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> PanCheckResponse:
    _ = principal  # presence-only — RBAC dep enforces SUBMIT_REFERRAL
    result = await service.realtime_pan_check(session, pan_plain=body.pan)
    cooling = result.cooling
    return PanCheckResponse(
        verdict=result.verdict,
        pan_masked=result.pan_masked,
        message=result.message,
        existing_referral_id=result.existing_referral_id,
        existing_status=result.existing_status,
        cooling_end=cooling.cooling_end if cooling else None,
        cooling_days_remaining=cooling.days_remaining if cooling else None,
        cooling_terminal_state=cooling.terminal_state if cooling else None,
        months_duration=cooling.months_duration if cooling else None,
        allow_override=result.allow_override,
    )


# ────────────────────────────────────────────────────────────────────
# GET /referrals/college-cap
# ────────────────────────────────────────────────────────────────────
@router.get(
    "/college-cap",
    response_model=CollegeCapStatus,
    dependencies=[Depends(require(Permission.SUBMIT_REFERRAL))],
    summary="Used / remaining referrals for (referrer, college).",
)
async def college_cap(
    principal: CurrentUser,
    college_id: UUID = Query(...),
    session: AsyncSession = Depends(get_session),
) -> CollegeCapStatus:
    cap = await validator.check_college_cap(
        session, referrer_id=principal.user_id, college_id=college_id
    )
    return CollegeCapStatus(
        college_id=cap.college_id,
        used=cap.used,
        limit=cap.limit,
        remaining=cap.remaining,
        can_submit=cap.can_submit,
        warning=cap.warning,
    )


# ────────────────────────────────────────────────────────────────────
# POST /referrals
# ────────────────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=ReferralSubmitResponse,
    status_code=201,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.SUBMIT_REFERRAL)),
    ],
    summary="Submit a complete referral form.",
)
async def submit_referral(
    body: ReferralSubmitRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralSubmitResponse:
    today = date.today()
    return await service.submit(
        session,
        referrer_id=principal.user_id,
        payload=body,
        today=today,
        current_year=today.year,
    )


# ────────────────────────────────────────────────────────────────────
# GET /referrals/me
# ────────────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=list[ReferralSummary],
    dependencies=[Depends(require(Permission.VIEW_OWN_REFERRALS))],
    summary="List referrals submitted by the current user.",
)
async def my_referrals(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[ReferralSummary]:
    rows = await repository.list_for_referrer(session, referrer_id=principal.user_id)
    return [_to_summary(r) for r in rows]


# ────────────────────────────────────────────────────────────────────
# GET /referrals/{id}
# ────────────────────────────────────────────────────────────────────
@router.get(
    "/{referral_id}",
    response_model=ReferralDetail,
    summary="Single referral. Visible to its referrer, mentor, HR, and PO.",
)
async def get_referral(
    referral_id: UUID,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> ReferralDetail:
    referral = await repository.get(session, referral_id)
    if referral is None:
        raise BusinessRuleError(
            user_message="Referral not found.", details={"referral_id": str(referral_id)}
        )

    # RBAC: HR + PO see everything. Referrer + mentor see their own only.
    is_owner = referral.referrer_id == principal.user_id
    is_mentor = referral.mentor_id == principal.user_id
    is_privileged = principal.role in (UserRole.HR, UserRole.PROGRAM_OWNER)
    if not (is_owner or is_mentor or is_privileged):
        # Use the standard permission error instead of leaking that the
        # referral exists.
        try:
            assert_permission(principal, Permission.VIEW_ALL_REFERRALS)
        except InsufficientPermissionsError:
            raise

    return ReferralDetail(
        **_to_summary(referral).model_dump(),
        candidate_phone=referral.candidate_phone,
        candidate_year_of_study=referral.candidate_year_of_study,
        candidate_graduation_year=referral.candidate_graduation_year,
        project_overview=referral.project_overview,
        joining_location=referral.joining_location,
        internship_start_date=referral.internship_start_date,
        internship_end_date=referral.internship_end_date,
        rejection_reason=referral.rejection_reason,
    )


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
def _to_summary(r) -> ReferralSummary:  # type: ignore[no-untyped-def]
    return ReferralSummary(
        id=r.id,
        status=r.status,
        current_stage=r.current_stage,
        candidate_name=r.candidate_name,
        candidate_email=r.candidate_email,
        pan_masked=r.candidate_pan_masked,
        college_id=r.college_id,
        project_title=r.project_title,
        submitted_at=r.submitted_at,
        mentor_id=r.mentor_id,
        mentor_attempt_count=r.mentor_attempt_count,
        created_at=r.created_at,
    )


# Re-exports for `app.main` import.
referral_router = router

# Suppress unused-import warning when the file is loaded standalone.
_ = college_repository
