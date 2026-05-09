"""Mentor action-token endpoints.

Decision B12: GET renders a confirmation page; POST executes.

Routes:
  GET  /action/mentor?token=<raw>&action=ACCEPT|REJECT
       → public (no SSO). Validates the token (without consuming it),
         returns metadata so the SPA can render either:
           * "Click to confirm acceptance" (ACCEPT)
           * "Tell us why you're declining" (REJECT)
       Pre-fetchers and email-link warmers don't trigger the action.

  POST /action/mentor/confirm
       → public; idempotent; consumes the token.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_session
from app.middleware.rate_limit import rate_limit
from app.modules.mentor import action_tokens, service
from app.modules.mentor.schemas import MentorActionConfirmRequest, MentorActionResponse
from app.shared.constants import ActionTokenType
from app.shared.exceptions import MentorRejectionReasonMissingError

router = APIRouter(prefix="/action/mentor", tags=["mentor-action"])
logger = logging.getLogger("nexhire.router.mentor")


class MentorActionPreviewResponse(BaseModel):
    valid: bool
    action: Literal["ACCEPT", "REJECT"]
    referral_id: str
    expires_at: str


@router.get(
    "",
    response_model=MentorActionPreviewResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Preview a mentor action without consuming the token (B12).",
)
async def preview(
    token: str = Query(..., min_length=10),
    action: Literal["ACCEPT", "REJECT"] = Query(...),
    session: AsyncSession = Depends(get_session),
) -> MentorActionPreviewResponse:
    row = await action_tokens.validate(
        session,
        raw_token=token,
        expected_action=ActionTokenType.MENTOR_RESPONSE,
        mark_used=False,
    )
    return MentorActionPreviewResponse(
        valid=True,
        action=action,
        referral_id=str(row.referral_id),
        expires_at=row.expires_at.isoformat(),
    )


@router.post(
    "/confirm",
    response_model=MentorActionResponse,
    dependencies=[Depends(rate_limit("unauth"))],
    summary="Consume a mentor token and apply the action (B12).",
)
async def confirm(
    body: MentorActionConfirmRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> MentorActionResponse:
    ip = request.client.host if request.client else None

    if body.action == "ACCEPT":
        assignment = await service.accept(
            session, raw_token=body.token, ip_address=ip
        )
        return MentorActionResponse(
            status="ACCEPTED",
            referral_id=str(assignment.referral_id),
            message="Thank you. You have accepted this mentoring assignment.",
        )

    # REJECT
    if not body.reason or len(body.reason.strip()) < 10:
        raise MentorRejectionReasonMissingError()

    assignment, is_terminal = await service.reject(
        session, raw_token=body.token, reason=body.reason, ip_address=ip
    )
    msg = "Your response has been recorded."
    if is_terminal:
        msg += " Maximum mentor attempts reached — the referral has been closed."
    return MentorActionResponse(
        status="REJECTED",
        referral_id=str(assignment.referral_id),
        is_terminal=is_terminal,
        message=msg,
    )
