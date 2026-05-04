"""Mentor module Pydantic schemas — HTTP I/O shapes."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MentorActionConfirmRequest(BaseModel):
    """Body of POST /action/mentor/confirm.

    `action`:  "ACCEPT" — token alone proves intent.
               "REJECT" — `reason` mandatory (≥10 chars per RULE-M4).
    """

    token: str = Field(..., min_length=10)
    action: str = Field(..., pattern="^(ACCEPT|REJECT)$")
    reason: str | None = None


class MentorActionResponse(BaseModel):
    status: str
    referral_id: str
    is_terminal: bool = False
    message: str
