"""AI-1 — Resume Deep Analyzer.

Two-phase extraction so the UI can fill basic fields immediately:

  Phase 1 — `parse_resume()` (fast, ~1-2s):
    Azure Document Intelligence OCRs the PDF/DOCX. Regex pulls out
    email, phone, and a candidate name guess. The full extracted text
    is cached by `document_id` so phase 2 doesn't re-OCR.

  Phase 2 — `analyze_resume_ai(document_id)` (slow, ~5-15s):
    Sends the cached text to GPT-4o for structured field extraction
    (year_of_study, graduation_year, college, skills, red_flags, etc.).
    The frontend calls this after phase 1 returns, while the user is
    already reviewing the basic fields.

`ParseResult` carries both phases' outputs (phase-2 fields are null
when only phase 1 has run). On any failure we always return a
`ParseResult` — caller falls back to manual entry.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.infrastructure import azure_openai
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
)

logger = logging.getLogger("nexhire.ai.resume")

MODEL_TOUCHPOINT = "RESUME_PARSE"

# In-process cache of OCR'd text keyed by Document.id. Phase 2 reads
# this so it doesn't have to re-OCR. 10 min TTL is plenty — the user
# will have either submitted or abandoned the form by then.
_TEXT_CACHE_TTL_SECONDS = 600
_text_cache: dict[UUID, tuple[float, str]] = {}


def _cache_set(document_id: UUID, text: str) -> None:
    expires_at = time.time() + _TEXT_CACHE_TTL_SECONDS
    _text_cache[document_id] = (expires_at, text)
    # Lazy GC: if cache grows large, evict expired entries.
    if len(_text_cache) > 200:
        now = time.time()
        for k in list(_text_cache.keys()):
            exp, _ = _text_cache[k]
            if exp < now:
                _text_cache.pop(k, None)


def _cache_get(document_id: UUID) -> str | None:
    entry = _text_cache.get(document_id)
    if entry is None:
        return None
    expires_at, text = entry
    if time.time() > expires_at:
        _text_cache.pop(document_id, None)
        return None
    return text


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
    degradation_reason: str | None = None
    user_message: str | None = None
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

_USER_PROMPT = """Extract these fields from the resume and return JSON.

For phase-2 fields the regex pass below already handled name/email/phone,
so set those three to {"value": null, "confidence": 0.0}.

{
  "candidate_name":          {"value": null, "confidence": 0.0},
  "email":                   {"value": null, "confidence": 0.0},
  "phone":                   {"value": null, "confidence": 0.0},
  "year_of_study":           {"value": 1|2|3|4|null, "confidence": 0.0-1.0},
  "college":                 {"value": "string|null", "confidence": 0.0-1.0},
  "graduation_year":         {"value": YYYY|null, "confidence": 0.0-1.0},
  "skills":                  ["..."],
  "red_flags":               ["..."],
  "suggested_project_tracks":     ["ML","Backend",...],
  "recommended_mentor_questions": ["..."],
  "education":               [],
  "technical_depth":         "Beginner|Intermediate|Advanced|Expert",
  "project_experience_quality":   "Low|Medium|High",
  "internship_readiness_score":   0-100
}

Rules:
- year_of_study: infer from "3rd year B.Tech" / "Currently in semester 5" / etc. (1=1st, 2=2nd, 3=3rd, 4=4th).
- graduation_year: integer like 2027.
- skills: max 15 items, lowercase, deduplicated.
- red_flags: gaps, fakes, inconsistencies. Empty list when none.
- internship_readiness_score: structural only (skills, projects, depth) — never college tier/gender/SES.
- Be conservative; null over guessing."""


# ────────────────────────────────────────────────────────────────────
# Phase 1 — fast: Doc Intelligence + regex.
# ────────────────────────────────────────────────────────────────────
async def parse_resume(
    file_bytes: bytes,
    mime_type: str,
    *,
    document_id: UUID | None = None,
) -> ParseResult:
    """Phase 1: OCR + regex extraction. Returns quickly with name/email/phone.

    The full extracted text is cached by `document_id` so the AI step
    (`analyze_resume_ai`) doesn't have to re-OCR. Pass `document_id`
    once you've persisted the Document row.

    Errors NEVER bubble out — we always return a ParseResult. The
    `succeeded=False` path is a normal degradation; the surrounding
    request continues with a manual-entry form.
    """
    try:
        # For images: skip Doc Intelligence (it's still PDF/text-oriented).
        # We only do regex on extracted text; images go straight to AI in
        # phase 2 via the legacy vision path.
        text: str | None = None
        if not mime_type.startswith("image/"):
            text = await _extract_text_via_doc_intelligence(file_bytes)
        if document_id is not None and text:
            _cache_set(document_id, text)

        if text:
            name, email, phone = _regex_extract_basics(text)
            return ParseResult(
                succeeded=True,
                data=_partial_data(name=name, email=email, phone=phone),
                confidence_scores={
                    "candidate_name": 0.6 if name else 0.0,
                    "candidate_email": 0.95 if email else 0.0,
                    "candidate_phone": 0.85 if phone else 0.0,
                    "year_of_study": 0.0,
                    "college": 0.0,
                    "graduation_year": 0.0,
                },
            )

        # Image MIME with no text path — leave fields empty, phase 2
        # (vision) will fill them.
        return ParseResult(
            succeeded=True,
            data=_partial_data(),
            confidence_scores={},
        )
    except Exception:
        logger.exception("nexhire.ai.resume.phase1_failed")
        return ParseResult(
            succeeded=False,
            degradation_reason="UNEXPECTED_ERROR",
            user_message="Auto-fill failed. Please fill in the details manually.",
        )


def _regex_extract_basics(text: str) -> tuple[str | None, str | None, str | None]:
    """Pull email, phone, and a name guess out of the OCR'd text."""
    email_match = re.search(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
    )
    email = email_match.group(0).lower() if email_match else None

    # Match Indian and intl phone formats; require 10+ digits to dodge
    # zip codes and stray years.
    phone_match = re.search(
        r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}",
        text,
    )
    phone: str | None = None
    if phone_match:
        candidate = re.sub(r"[^\d+]", "", phone_match.group(0))
        if len(candidate.lstrip("+")) >= 10:
            phone = candidate

    # Name guess: first non-empty line that doesn't contain "@" or digits
    # and is 2-5 words. Resumes overwhelmingly start with the candidate's
    # name in the first 1-2 lines.
    name: str | None = None
    for line in (s.strip() for s in text.splitlines()[:8]):
        if not line:
            continue
        if "@" in line or re.search(r"\d", line):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(w[:1].isalpha() for w in words if w):
            name = line
            break

    return name, email, phone


def _partial_data(
    *,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> ResumeJson:
    """Build a `ResumeJson` populated with whatever phase 1 extracted.

    Phase 2 fields default to nulls / empty lists. The frontend treats
    confidence=0 fields as "not extracted" and won't badge them.
    """
    return ResumeJson(
        candidate_name=FieldWithConfidence(
            value=name, confidence=0.6 if name else 0.0
        ),
        email=FieldWithConfidence(value=email, confidence=0.95 if email else 0.0),
        phone=FieldWithConfidence(value=phone, confidence=0.85 if phone else 0.0),
        year_of_study=FieldWithConfidence(value=None, confidence=0.0),
        college=FieldWithConfidence(value=None, confidence=0.0),
        graduation_year=FieldWithConfidence(value=None, confidence=0.0),
    )


# ────────────────────────────────────────────────────────────────────
# Phase 2 — slow: GPT-4o structured analysis.
# ────────────────────────────────────────────────────────────────────
async def analyze_resume_ai(document_id: UUID) -> ParseResult:
    """Phase 2: pull cached OCR text and ask GPT-4o for the rest of the
    fields (year_of_study, graduation_year, college, skills, red flags).

    Returns `succeeded=False, degradation_reason="EXPIRED"` if the cache
    entry has expired (e.g. browser tab open longer than 10 min).
    """
    text = _cache_get(document_id)
    if text is None:
        return ParseResult(
            succeeded=False,
            degradation_reason="EXPIRED",
            user_message=(
                "AI analysis expired. Please re-upload the resume to continue."
            ),
        )

    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        return ParseResult(
            succeeded=False,
            degradation_reason="AI_NOT_CONFIGURED",
            user_message="AI analysis is unavailable. Please fill in the details manually.",
        )

    try:
        return await _attempt_ai_analysis(text)
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
            user_message="AI is temporarily unavailable. Please fill in the details manually.",
        )
    except Exception:
        logger.exception("nexhire.ai.resume.unexpected")
        return ParseResult(
            succeeded=False,
            degradation_reason="UNEXPECTED_ERROR",
            user_message="AI analysis failed unexpectedly. Please fill in the details manually.",
        )


async def _attempt_ai_analysis(extracted_text: str) -> ParseResult:
    import time

    cfg = get_settings()
    client = azure_openai.get_client()
    deployment = cfg.azure_openai_deployment_gpt4o

    # Resumes rarely have more than ~3-5K chars of useful content.
    # Capping at 8K keeps GPT-4o's input tokens low so prompt-processing
    # is fast (a major chunk of latency at this scale).
    user_content = [
        {"type": "text", "text": _USER_PROMPT},
        {
            "type": "text",
            "text": (
                "\n\n[Resume text extracted via Azure Document Intelligence:]\n"
                + extracted_text[:8_000]
            ),
        },
    ]

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
        # Tighter cap — output is the bottleneck (token-by-token gen at
        # ~50/s). A focused phase-2 schema fits in ~700 tokens.
        max_tokens=1_000,
        timeout=30.0,
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
async def _build_user_content_async(
    file_bytes: bytes, mime_type: str
) -> list[dict[str, Any]]:
    """Build the user-message content parts for GPT-4o.

    Image MIME types go directly via vision (image_url). PDF/DOCX are
    OCR'd via Azure Document Intelligence's `prebuilt-read` model first;
    the extracted plain text is then sent to GPT-4o for structured
    field extraction. Without this step PDFs send unreadable base64
    blobs and GPT-4o returns all-null fields.
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
        return parts

    extracted = await _extract_text_via_doc_intelligence(file_bytes)
    if extracted:
        parts.append(
            {
                "type": "text",
                "text": (
                    "\n\n[Resume text extracted via Azure Document Intelligence:]"
                    f"\n{extracted[:30_000]}"
                ),
            }
        )
    else:
        # Last-resort fallback: if Doc Intelligence isn't available the
        # base64 blob is unreadable but at least gives the model the
        # original mime hint so it can degrade explicitly.
        b64 = base64.b64encode(file_bytes).decode("ascii")
        parts.append(
            {
                "type": "text",
                "text": (
                    f"\n\n[Resume payload could not be OCR'd (mime={mime_type}, "
                    f"{len(file_bytes)} bytes). Return all fields as null with "
                    f"confidence=0 if you cannot read the content.]"
                    f"\n{b64[:4000]}"
                ),
            }
        )
    return parts


async def _extract_text_via_doc_intelligence(file_bytes: bytes) -> str | None:
    """OCR / text-extract via Azure Document Intelligence's `prebuilt-read`.

    Returns the joined text content (lines newline-separated) or None
    if Doc Intelligence isn't configured / fails. The caller falls back
    to a degraded path when None.
    """
    from app.config import get_settings as _gs

    cfg = _gs()
    if not cfg.azure_doc_intelligence_endpoint or not cfg.azure_doc_intelligence_key:
        logger.info("nexhire.ai.resume.doc_intel_not_configured")
        return None
    try:
        from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=cfg.azure_doc_intelligence_endpoint,
            credential=AzureKeyCredential(cfg.azure_doc_intelligence_key),
            polling_interval=1.0,  # default is 5s; resumes finish in seconds
        )
        t0 = time.monotonic()
        async with client:
            t1 = time.monotonic()
            poller = await client.begin_analyze_document(
                model_id="prebuilt-read",
                body={"base64Source": base64.b64encode(file_bytes).decode("ascii")},
                polling_interval=1.0,
            )
            t2 = time.monotonic()
            result = await poller.result()
            t3 = time.monotonic()
        logger.info(
            "nexhire.ai.resume.doc_intel_timing",
            extra={
                "client_setup_ms": int((t1 - t0) * 1000),
                "submit_ms": int((t2 - t1) * 1000),
                "polling_ms": int((t3 - t2) * 1000),
                "total_ms": int((t3 - t0) * 1000),
                "bytes": len(file_bytes),
            },
        )
    except Exception as exc:
        logger.warning("nexhire.ai.resume.doc_intel_failed", exc_info=exc)
        return None

    # Prefer the top-level `content` field (full document text); fall back
    # to concatenating page lines for older SDK shapes.
    content = getattr(result, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    pages = getattr(result, "pages", None) or []
    chunks: list[str] = []
    for page in pages:
        for line in getattr(page, "lines", None) or []:
            text = getattr(line, "content", None)
            if text:
                chunks.append(str(text))
    if not chunks:
        return None
    return "\n".join(chunks)


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
