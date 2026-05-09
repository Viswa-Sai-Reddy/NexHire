"""Candidate portal endpoints — /candidate/* (no SSO, magic-link auth).

  POST /candidate/redeem            — token → JWT + redirect path
  GET  /candidate/intern            — current intern record (status, dates)
  GET  /candidate/joining-form      — draft for the authenticated candidate
  PATCH /candidate/joining-form     — auto-save draft (optimistic lock)
  POST /candidate/joining-form/submit
                                    — DRAFT/SUBMITTED → SUBMITTED, runs
                                      auto-lock engine.
  POST /candidate/joining-form/extract-id-doc
                                    — multipart upload; AI-6 returns
                                      structured fields.
  GET  /candidate/nda               — render NDA agreement HTML + sha256.
  POST /candidate/nda/accept        — click-to-accept; records typed name,
                                      IP, UA, text hash into nda_records.

HR-side companion (separate router):
  POST /hr/onboarding/joining-form/{intern_id}/lock
                                    — manual HR lock after review.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.modules.ai import form_assistant
from app.modules.auth.rbac import Permission, require
from app.modules.nda import service as nda_service
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
from app.modules.referral.models import Referral
from app.shared.constants import UserRole
from app.shared.exceptions import (
    CandidateRecordMismatchError,
    InsufficientPermissionsError,
)

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


class CandidateLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    non_worker_id: str = Field(..., min_length=3, max_length=64)


class CandidateLoginResponse(BaseModel):
    access_token: str
    expires_in: int
    redirect_to: str
    intern_id: UUID


@candidate_router.post(
    "/login",
    response_model=CandidateLoginResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Candidate sign-in via email + Non-Worker ID.",
)
async def candidate_login(
    body: CandidateLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateLoginResponse:
    """Issues a candidate JWT when (email, non_worker_id) match an
    existing candidate user + their intern. The candidate must have
    completed the joining-form / NDA flow once — the Non-Worker ID is
    generated then. Pre-NDA candidates use the magic link from their
    initial joining-form invitation email.
    """
    from app.modules.auth import jwt_service
    from app.modules.auth.models import User as AuthUser
    from app.shared.exceptions import BusinessRuleError

    email = body.email.strip().lower()
    non_worker_id = body.non_worker_id.strip().upper()

    user = (
        await session.execute(
            select(AuthUser).where(
                AuthUser.email == email,
                AuthUser.role == UserRole.CANDIDATE.value,
                AuthUser.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    intern: Intern | None = None
    if user is not None:
        intern = (
            await session.execute(
                select(Intern).where(
                    Intern.user_id == user.id,
                    Intern.non_worker_id == non_worker_id,
                )
            )
        ).scalar_one_or_none()

    if user is None or intern is None:
        logger.info(
            f"candidate_login: invalid credentials for email={email!r}"
        )
        raise BusinessRuleError(
            user_message="Invalid email or Non-Worker ID.",
            details={"reason": "credentials_mismatch"},
        )

    access_token, expires_in = jwt_service.issue_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        can_mentor=False,
        intern_id=intern.id,
    )

    redirect = await magic_link._redirect_for_status(intern, session)

    logger.info(
        f"candidate_login: issued JWT for user={user.id} intern={intern.id}"
    )
    return CandidateLoginResponse(
        access_token=access_token,
        expires_in=expires_in,
        redirect_to=redirect,
        intern_id=intern.id,
    )


class RequestMagicLinkRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


@candidate_router.post(
    "/request-magic-link",
    status_code=204,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Email a fresh sign-in magic link to a candidate. Always 204.",
)
async def request_magic_link(
    body: RequestMagicLinkRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Recovery flow for candidates who forgot their Non-Worker ID.
    Returns 204 regardless of whether the email matches a candidate, so
    the endpoint can't be used to enumerate accounts. If the email maps
    to a candidate user with an intern, `magic_link.issue_fresh_link`
    mints a fresh CANDIDATE_ACCESS token and the existing
    `CandidateMagicLinkIssued` notification handler emails the link.
    """
    from app.modules.auth.models import User as AuthUser

    email = body.email.strip().lower()

    user = (
        await session.execute(
            select(AuthUser).where(
                AuthUser.email == email,
                AuthUser.role == UserRole.CANDIDATE.value,
                AuthUser.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if user is None:
        logger.info(f"request_magic_link: no candidate for email {email!r}")
        return None

    # A candidate can have multiple intern rows over time (re-referrals
    # after cooling). Pick the most recent — that's the active onboarding.
    intern = (
        await session.execute(
            select(Intern)
            .where(Intern.user_id == user.id)
            .order_by(Intern.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if intern is None:
        logger.info(f"request_magic_link: candidate {user.id} has no intern row")
        return None

    await magic_link.issue_fresh_link(session, intern_id=intern.id)
    logger.info(f"request_magic_link: fresh magic link issued for intern {intern.id}")
    return None


class CandidateInternResponse(BaseModel):
    intern_id: UUID
    referral_id: UUID
    status: str
    candidate_name: str
    non_worker_id: str | None
    project_title: str | None
    actual_start_date: date | None
    actual_end_date: date | None
    internship_start_date: date | None
    internship_end_date: date | None


@candidate_router.get(
    "/certificate",
    dependencies=[Depends(require(Permission.COMPLETE_JOINING_FORM))],
    summary="Issue a short-lived URL to download the candidate's certificate.",
)
async def get_certificate_url(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    from app.infrastructure import azure_blob
    from app.modules.referral.models import Document
    from app.shared.constants import DocumentType
    from app.shared.exceptions import BusinessRuleError

    intern_id = await _intern_for(principal, session)
    document = (
        await session.execute(
            select(Document)
            .where(
                Document.document_type == DocumentType.CERTIFICATE.value,
                Document.azure_blob_key == f"certificates/{intern_id}.pdf",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if document is None:
        raise BusinessRuleError(
            user_message=(
                "Your certificate isn't ready yet. It will be available "
                "shortly after your mentor confirms completion."
            )
        )

    url = await azure_blob.generate_sas_url(
        document.azure_blob_container,
        document.azure_blob_key,
        minutes_valid=15,
    )
    return {"url": url, "file_name": document.file_name}


@candidate_router.get(
    "/intern",
    response_model=CandidateInternResponse,
    dependencies=[Depends(require(Permission.COMPLETE_JOINING_FORM))],
    summary="Authenticated candidate fetches their intern record.",
)
async def get_intern_endpoint(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> CandidateInternResponse:
    intern_id = await _intern_for(principal, session)
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(select(Referral).where(Referral.id == intern.referral_id))
    ).scalar_one()
    return CandidateInternResponse(
        intern_id=intern.id,
        referral_id=referral.id,
        status=intern.status,
        candidate_name=referral.candidate_name,
        non_worker_id=intern.non_worker_id,
        project_title=referral.project_title,
        actual_start_date=intern.actual_start_date,
        actual_end_date=intern.actual_end_date,
        internship_start_date=referral.internship_start_date,
        internship_end_date=referral.internship_end_date,
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
    # Note: persistence + cross-validation happens at submit time via
    # the auto-lock engine; this endpoint is a real-time helper only.
    _ = session
    return IdDocExtractResponse(
        succeeded=result.succeeded,
        name=result.name,
        dob=result.dob,
        id_number=result.id_number,
        pan_number=result.pan_number,
        degradation_reason=result.degradation_reason,
    )


class CandidateNdaResponse(BaseModel):
    intern_id: UUID
    status: str
    candidate_name: str
    text_html: str
    text_sha256: str
    signed_at: datetime | None = None
    typed_name: str | None = None


class CandidateNdaAcceptRequest(BaseModel):
    typed_name: str = Field(..., min_length=1, max_length=255)
    text_sha256: str = Field(..., min_length=64, max_length=64)


@candidate_router.get(
    "/nda",
    response_model=CandidateNdaResponse,
    dependencies=[Depends(require(Permission.COMPLETE_JOINING_FORM))],
    summary="Render the NDA agreement HTML for in-app click-to-accept.",
)
async def get_nda_endpoint(
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> CandidateNdaResponse:
    intern_id = await _intern_for(principal, session)
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(select(Referral).where(Referral.id == intern.referral_id))
    ).scalar_one()

    record = await nda_service._by_intern_id(session, intern_id)
    text_html, text_sha256 = await nda_service.render_nda_html(
        candidate_name=referral.candidate_name
    )
    return CandidateNdaResponse(
        intern_id=intern_id,
        status=record.status,
        candidate_name=referral.candidate_name,
        text_html=text_html,
        text_sha256=text_sha256,
        signed_at=record.signed_at,
        typed_name=record.typed_name,
    )


@candidate_router.post(
    "/nda/accept",
    response_model=CandidateNdaResponse,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.COMPLETE_JOINING_FORM)),
    ],
    summary="Click-to-accept the NDA. Records typed name + IP + UA + text hash.",
)
async def accept_nda_endpoint(
    body: CandidateNdaAcceptRequest,
    principal: CurrentUser,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> CandidateNdaResponse:
    intern_id = await _intern_for(principal, session)
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(select(Referral).where(Referral.id == intern.referral_id))
    ).scalar_one()

    text_html, _ = await nda_service.render_nda_html(
        candidate_name=referral.candidate_name
    )
    record = await nda_service.accept_inapp(
        session,
        intern_id=intern_id,
        typed_name=body.typed_name,
        text_sha256=body.text_sha256,
        template_text=text_html,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    # Re-render to return the same payload shape as GET (handy for the
    # frontend to flip into the "signed" view after accept without a
    # second roundtrip).
    return CandidateNdaResponse(
        intern_id=intern_id,
        status=record.status,
        candidate_name=referral.candidate_name,
        text_html=text_html,
        text_sha256=body.text_sha256,
        signed_at=record.signed_at,
        typed_name=record.typed_name,
    )


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
async def _intern_for(
    principal: CurrentUser, session: AsyncSession
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


# ────────────────────────────────────────────────────────────────────
# HR-side joining-form endpoints — /hr/onboarding/*.
# Separate router because the candidate router enforces CANDIDATE-only
# RBAC via COMPLETE_JOINING_FORM.
# ────────────────────────────────────────────────────────────────────
hr_onboarding_router = APIRouter(
    prefix="/hr/onboarding", tags=["hr-onboarding"]
)


class JoiningFormLockRequest(BaseModel):
    notes: str | None = Field(None, max_length=2000)


@hr_onboarding_router.post(
    "/joining-form/{intern_id}/lock",
    response_model=JoiningFormDraft,
    dependencies=[
        Depends(rate_limit("default")),
        Depends(require(Permission.LOCK_JOINING_FORM)),
    ],
    summary="HR manually locks a flagged joining form (S13/S14).",
)
async def hr_lock_joining_form(
    intern_id: UUID,
    body: JoiningFormLockRequest,
    principal: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> JoiningFormDraft:
    form = await service.manual_lock(
        session,
        intern_id=intern_id,
        hr_user_id=principal.user_id,
        hr_role=principal.role,
        notes=body.notes,
    )
    return _form_to_dto(form, intern_id=intern_id)
