"""Pydantic schemas for the candidate portal."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CandidateRedeemRequest(BaseModel):
    token: str = Field(..., min_length=10)


class CandidateRedeemResponse(BaseModel):
    access_token: str
    expires_in: int
    redirect_to: str
    intern_id: UUID


class JoiningFormDraft(BaseModel):
    intern_id: UUID
    status: str
    version: int
    personal_details: dict[str, Any]
    address: dict[str, Any]
    emergency_contact: dict[str, Any]
    education_history: list[Any]
    employment_history: list[Any]
    govt_ids: dict[str, Any]
    uploaded_documents: list[Any]
    declaration_signed: bool
    submitted_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by_label: str | None = None
    updated_at: datetime


class JoiningFormSaveRequest(BaseModel):
    expected_version: int
    personal_details: dict[str, Any] | None = None
    address: dict[str, Any] | None = None
    emergency_contact: dict[str, Any] | None = None
    education_history: list[Any] | None = None
    employment_history: list[Any] | None = None
    govt_ids: dict[str, Any] | None = None
    uploaded_documents: list[Any] | None = None
    declaration_signed: bool | None = None


class IdDocExtractResponse(BaseModel):
    succeeded: bool
    name: str | None = None
    dob: date | None = None
    id_number: str | None = None
    pan_number: str | None = None
    degradation_reason: str | None = None


class JoiningFormSubmitResponse(BaseModel):
    decision: str  # AUTO_LOCK (auto-lock engine no longer routes to HR)
    high_flags: list[str] = Field(default_factory=list)
    low_flags: list[str] = Field(default_factory=list)
    next_redirect: str
