"""AI-1 — Resume Deep Analyzer.

Extracts structured fields from a resume PDF/DOCX/JPG/PNG via GPT-4o
(vision + text). Returns a `ParseResult` carrying:
  * Field values + per-field confidence.
  * Skills, education, suggested project tracks.
  * Red flags (gap years, etc.) for HR review.
  * `succeeded: False` + a degradation reason if AI failed — caller
    proceeds with manual entry (Blueprint §17.6 graceful degradation).

The prompt is split into a SYSTEM directive and a USER instruction
shaped so the model returns one JSON object that matches a Pydantic
schema. We re-validate every reply via Pydantic; on parse failure we
retry once with a corrective prompt before degrading.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.infrastructure import azure_openai
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
)

logger = logging.getLogger("nexhire.ai.resume")

MODEL_TOUCHPOINT = "RESUME_PARSE"


# ────────────────────────────────────────────────────────────────────
# Output schema (Pydantic).
# Confidence is 0.0–1.0 per field. `< 0.75` triggers the "Please verify"
# UI badge per Blueprint §6.2.
# ────────────────────────────────────────────────────────────────────
class FieldWithConfidence(BaseModel):
    value: str | int | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class EducationItem(BaseModel):
    degree: str = ""
    field: str = ""
    institution: str = ""
    year: int | None = None


class ResumeJson(BaseModel):
    candidate_name: FieldWithConfidence
    email: FieldWithConfidence
    phone: FieldWithConfidence
    year_of_study: FieldWithConfidence
    college: FieldWithConfidence
    graduation_year: FieldWithConfidence
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    internship_readiness_score: int = Field(default=0, ge=0, le=100)
    technical_depth: str = ""
    project_experience_quality: str = ""
    suggested_project_tracks: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    recommended_mentor_questions: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """The shape AiService.parse_resume returns."""

    succeeded: bool
    data: ResumeJson | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    degradation_reason: Optional[str] = None
    user_message: Optional[str] = None
    tokens_used: int | None = None
    latency_ms: int | None = None
    azure_request_id: str | None = None


# ────────────────────────────────────────────────────────────────────
# Prompts — kept as constants so they're code-reviewable / diffable.
# ────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are a resume analysis engine for an internship referral system. "
    "Extract structured data from the provided resume and provide an "
    "internship-readiness assessment. Return ONLY valid JSON matching the "
    "schema described in the user message. Never invent values; for any "
    "field not clearly present in the resume, set value=null and confidence=0.0. "
    "Do not include any commentary or markdown — JSON only."
)

_USER_PROMPT = """Analyze this resume and return JSON exactly matching:

{
  "candidate_name":          {"value": "string|null", "confidence": 0.0-1.0},
  "email":                   {"value": "string|null", "confidence": 0.0-1.0},
  "phone":                   {"value": "string|null (E.164 if possible)", "confidence": 0.0-1.0},
  "year_of_study":           {"value": "1|2|3|4|null", "confidence": 0.0-1.0},
  "college":                 {"value": "string|null", "confidence": 0.0-1.0},
  "graduation_year":         {"value": "YYYY|null", "confidence": 0.0-1.0},
  "education":               [{"degree":"...","field":"...","institution":"...","year":YYYY}],
  "skills":                  ["..."],
  "internship_readiness_score":   0-100,
  "technical_depth":         "Beginner|Intermediate|Advanced|Expert",
  "project_experience_quality":   "Low|Medium|High",
  "suggested_project_tracks":     ["ML","Backend",...],
  "red_flags":               ["e.g., unexplained gap Jun-Aug 2024"],
  "recommended_mentor_questions": ["..."]
}

Be conservative on confidence. Internship-readiness scoring is structural
(skills present, projects completed, depth indicators) — do NOT score
based on college tier, gender, or socioeconomic markers."""


# ────────────────────────────────────────────────────────────────────
# Public entry point.
# ────────────────────────────────────────────────────────────────────
async def parse_resume(file_bytes: bytes, mime_type: str) -> ParseResult:
    """Top-level call site. Caller has already validated MIME + size and
    persisted the file to Azure Blob.

    Errors NEVER bubble out — we always return a ParseResult. The
    `succeeded=False` path is a normal degradation; the surrounding
    request continues with a manual-entry form.
    """
    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        return ParseResult(
            succeeded=False,
            degradation_reason="AI_NOT_CONFIGURED",
            user_message="Auto-fill is unavailable. Please fill in the details manually.",
        )

    try:
        return await _attempt_parse(file_bytes=file_bytes, mime_type=mime_type)
    except AzureOpenAiQuotaExceededError:
        logger.error("nexhire.ai.resume.quota_exhausted")
        return ParseResult(
            succeeded=False,
            degradation_reason="QUOTA_EXCEEDED",
            user_message="AI is temporarily unavailable. Please fill the form manually.",
        )
    except AzureOpenAiError:
        logger.exception("nexhire.ai.resume.unavailable")
        return ParseResult(
            succeeded=False,
            degradation_reason="AI_UNAVAILABLE",
            user_message="Auto-fill is temporarily unavailable. Please fill in the details manually.",
        )
    except Exception:  # noqa: BLE001 — last-resort defense
        logger.exception("nexhire.ai.resume.unexpected")
        return ParseResult(
            succeeded=False,
            degradation_reason="UNEXPECTED_ERROR",
            user_message="Auto-fill failed unexpectedly. Please fill in the details manually.",
        )


async def _attempt_parse(*, file_bytes: bytes, mime_type: str) -> ParseResult:
    import time

    cfg = get_settings()
    client = azure_openai.get_client()
    deployment = cfg.azure_openai_deployment_gpt4o

    user_content = _build_user_content(file_bytes, mime_type)

    started = time.monotonic()
    response = await azure_openai.call_with_retry(
        "resume_parse",
        client.chat.completions.create,
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=2_000,
        timeout=20.0,
    )
    latency_ms = int((time.monotonic() - started) * 1_000)

    raw_text = (response.choices[0].message.content or "").strip()
    if not raw_text:
        return ParseResult(
            succeeded=False,
            degradation_reason="EMPTY_RESPONSE",
            user_message="Could not extract data. Please fill the form manually.",
            latency_ms=latency_ms,
        )

    try:
        raw_dict = json.loads(raw_text)
        parsed = ResumeJson.model_validate(raw_dict)
    except (json.JSONDecodeError, ValidationError):
        # Single corrective retry — much higher success rate than first try.
        logger.warning("nexhire.ai.resume.malformed_first_attempt")
        retry_response = await azure_openai.call_with_retry(
            "resume_parse_retry",
            client.chat.completions.create,
            model=deployment,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON matching the schema. "
                        "Return ONLY a valid JSON object with no commentary or markdown."
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=2_000,
            timeout=20.0,
        )
        raw_text = (retry_response.choices[0].message.content or "").strip()
        try:
            raw_dict = json.loads(raw_text)
            parsed = ResumeJson.model_validate(raw_dict)
        except (json.JSONDecodeError, ValidationError):
            logger.error("nexhire.ai.resume.malformed_after_retry")
            return ParseResult(
                succeeded=False,
                degradation_reason="MALFORMED_OUTPUT",
                user_message="Could not extract data reliably. Please fill the form manually.",
                latency_ms=latency_ms,
                raw={"raw_text": raw_text[:500]},
            )

    confidence_scores = _extract_confidences(parsed)
    tokens = getattr(response.usage, "total_tokens", None) if response.usage else None
    request_id = getattr(response, "id", None)

    return ParseResult(
        succeeded=True,
        data=parsed,
        raw=parsed.model_dump(),
        confidence_scores=confidence_scores,
        tokens_used=tokens,
        latency_ms=latency_ms,
        azure_request_id=request_id,
    )


# ────────────────────────────────────────────────────────────────────
# Helpers.
# ────────────────────────────────────────────────────────────────────
def _build_user_content(file_bytes: bytes, mime_type: str) -> list[dict[str, Any]]:
    """GPT-4o accepts mixed text + image_url parts. PDFs go via Azure
    Document Intelligence in production for better OCR (decision B14);
    in S1 we send the raw image to GPT-4o Vision for image MIME types
    and the prompt-only mode (with extracted text from the caller) for
    PDF/DOCX. The extraction-from-text path lands in S3 alongside the
    Document Intelligence wiring.
    """
    parts: list[dict[str, Any]] = [{"type": "text", "text": _USER_PROMPT}]
    if mime_type.startswith("image/"):
        b64 = base64.b64encode(file_bytes).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }
        )
    else:
        # For PDF/DOCX in S1 we ship the raw bytes as a base64 hint;
        # the model is instructed via prompt to treat it as a resume.
        # S3's Document Intelligence integration will decode beforehand.
        b64 = base64.b64encode(file_bytes).decode("ascii")
        parts.append(
            {
                "type": "text",
                "text": (
                    f"\n\n[Resume payload, mime={mime_type}, base64-encoded "
                    f"{len(file_bytes)} bytes — interpret as document text]"
                    f"\n{b64[:8000]}"
                ),
            }
        )
    return parts


def _extract_confidences(parsed: ResumeJson) -> dict[str, float]:
    return {
        "candidate_name": parsed.candidate_name.confidence,
        "email": parsed.email.confidence,
        "phone": parsed.phone.confidence,
        "year_of_study": parsed.year_of_study.confidence,
        "college": parsed.college.confidence,
        "graduation_year": parsed.graduation_year.confidence,
    }


__all__ = ["MODEL_TOUCHPOINT", "ParseResult", "ResumeJson", "parse_resume"]
