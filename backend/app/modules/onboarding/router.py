"""Candidate portal endpoints — /candidate/* (no SSO, magic-link auth).

  POST /candidate/redeem            — token → JWT + redirect path
  GET  /candidate/joining-form      — draft for the authenticated candidate
  PATCH /candidate/joining-form     — auto-save draft (optimistic lock)
  POST /candidate/joining-form/submit
                                    — DRAFT/SUBMITTED → SUBMITTED, runs
                                      auto-lock engine.
  POST /candidate/joining-form/extract-id-doc
                                    — multipart upload; AI-6 returns
                                      structured fields.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.ai import form_assistant
from app.modules.auth.rbac import Permission, require
from app.modules.onboarding import magic_link, service
from app.modules.onboarding.models import Intern, JoiningForm
from app.modules.onboarding.schemas import (
    CandidateRedeemRequest,
    CandidateRedeemResponse,
    IdDocExtractResponse,
    JoiningFormDraft,
    JoiningFormSaveRequest,
    JoiningFormSubmitResponse,
)
from app.shared.constants import UserRole
from app.shared.exceptions import (
    CandidateRecordMismatchError,
    InsufficientPermissionsError,
)
from sqlalchemy import select


logger = logging.getLogger("nexhire.router.candidate")

candidate_router = APIRouter(prefix="/candidate", tags=["candidate"])


@candidate_router.post(
    "/redeem",
    response_model=CandidateRedeemResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Magic-link → candidate JWT (F-03).",
)
async def redeem(
    body: CandidateRedeemRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CandidateRedeemResponse:
    ip = request.client.host if request.client else None
    _, intern, access_token, expires_in, redirect = await magic_link.redeem(
        session, raw_token=body.token, ip_address=ip
    )
    return CandidateRedeemResponse(
        access_token=access_token,
        expires_in=expires_in,
        redirect_to=redirect,
        intern_id=intern.id,
    )


@candidate_router.get(
    "/joining-form",
    response_model=JoiningFormDraft,
    dependencies=[Depends(require(Permission.COMPLETE_JOINING_FORM))],
    summary="Authenticated candidate fetches their draft.",
)
async def get_form_endpoint(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> JoiningFormDraft:
    intern_id = await _intern_for(principal, session)
    form = await service.get_form(session, intern_id=intern_id)
    return _form_to_dto(form, intern_id=intern_id)


@candidate_router.patch(
    "/joining-form",
    response_model=JoiningFormDraft,
    dependencies=[Depends(require(Permission.COMPLETE_JOINING_FORM))],
    summary="Auto-save draft (every 60s).",
)
async def save_draft_endpoint(
    body: JoiningFormSaveRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> JoiningFormDraft:
    intern_id = await _intern_for(principal, session)
    fields = body.model_dump(exclude={"expected_version"}, exclude_none=True)
    form = await service.save_draft(
        session,
        intern_id=intern_id,
        expected_version=body.expected_version,
        fields=fields,
    )
    return _form_to_dto(form, intern_id=intern_id)


@candidate_router.post(
    "/joining-form/submit",
    response_model=JoiningFormSubmitResponse,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.COMPLETE_JOINING_FORM)),
    ],
    summary="Submit the joining form. Auto-lock engine fires.",
)
async def submit_form_endpoint(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> JoiningFormSubmitResponse:
    intern_id = await _intern_for(principal, session)
    result = await service.submit(session, intern_id=intern_id)
    return JoiningFormSubmitResponse(
        decision=result.decision,
        high_flags=[f.message for f in result.high_flags],
        low_flags=[f.message for f in result.low_flags],
        next_redirect="/candidate/nda" if result.decision == "AUTO_LOCK" else "/candidate/status",
    )


@candidate_router.post(
    "/joining-form/extract-id-doc",
    response_model=IdDocExtractResponse,
    dependencies=[
        Depends(rate_limit("ai")),
        Depends(require(Permission.COMPLETE_JOINING_FORM)),
    ],
    summary="AI-6: extract name/DOB/PAN from an uploaded ID document.",
)
async def extract_id_doc_endpoint(
    principal: CurrentUser,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> IdDocExtractResponse:
    _ = principal  # presence-only guard
    raw = await file.read()
    result = await form_assistant.extract_id_doc(
        raw, mime_type=file.content_type or "application/octet-stream"
    )
    return IdDocExtractResponse(
        succeeded=result.succeeded,
        name=result.name,
        dob=result.dob,
        id_number=result.id_number,
        pan_number=result.pan_number,
        degradation_reason=result.degradation_reason,
    )
    # Note: persistence + cross-validation happens at submit time via
    # the auto-lock engine; this endpoint is a real-time helper only.
    _ = session


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
async def _intern_for(
    principal: "CurrentUser", session: AsyncSession
) -> UUID:
    """Resolve the intern row for the authenticated candidate JWT.

    The candidate JWT always carries `intern_id`; if it doesn't, the
    token came from another role and shouldn't reach this router (the
    permission decorator screens for COMPLETE_JOINING_FORM, only granted
    to CANDIDATE).
    """
    if principal.role is not UserRole.CANDIDATE:
        raise InsufficientPermissionsError()
    if principal.intern_id is None:
        raise CandidateRecordMismatchError()
    intern = (
        await session.execute(
            select(Intern).where(Intern.id == principal.intern_id)
        )
    ).scalar_one_or_none()
    if intern is None or intern.user_id != principal.user_id:
        raise CandidateRecordMismatchError()
    return intern.id


def _form_to_dto(form: JoiningForm, *, intern_id: UUID) -> JoiningFormDraft:
    return JoiningFormDraft(
        intern_id=intern_id,
        status=form.status,
        version=form.version,
        personal_details=form.personal_details,
        address=form.address,
        emergency_contact=form.emergency_contact,
        education_history=form.education_history,
        employment_history=form.employment_history,
        govt_ids=form.govt_ids,
        uploaded_documents=form.uploaded_documents,
        declaration_signed=form.declaration_signed,
        submitted_at=form.submitted_at,
        locked_at=form.locked_at,
        locked_by_label=form.locked_by_label,
        updated_at=form.updated_at,
    )
