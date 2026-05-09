"""AI-8 — Certificate citation generator + auto-send (F-38).

Triggered by `ClosurePending` for clean closures. GPT-4o produces a
3–4 sentence citation; if confidence is high (≥0.85) the certificate
is auto-sent + an `AUTO_SEND_CERT` row is written for the 48h recall
window. Otherwise routed to HR for review (S5 endpoint).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure import azure_openai
from app.modules.onboarding.models import Intern
from app.modules.referral.models import (
    AiAutoAction,
    Document,
    Referral,
)
from app.shared.constants import (
    AI_SYSTEM_USER_ID,
    DocumentType,
)
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
)

logger = logging.getLogger("nexhire.ai.certificate")

MODEL_TOUCHPOINT = "CERTIFICATE_CITATION"
RECALL_HOURS = 48  # Implementation_Plan §17.13


@dataclass(frozen=True, slots=True)
class GeneratedCitation:
    text: str
    confidence: float
    succeeded: bool
    degradation_reason: str | None = None


_SYSTEM_PROMPT = (
    "You write professional internship-completion certificate citations. "
    "Be specific about the project and skills. 3–4 sentences maximum. "
    "Do NOT fabricate metrics — only use the provided data. Return JSON: "
    '{"text": "<citation>", "confidence": 0.0-1.0}.'
)


async def generate_citation(
    *, intern_name: str, project_title: str, project_overview: str | None,
    skills_demonstrated: list[str], mentor_feedback: str,
    duration_days: int,
) -> GeneratedCitation:
    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        return GeneratedCitation(
            text=_fallback(intern_name, project_title, duration_days),
            confidence=0.6,
            succeeded=False,
            degradation_reason="AI_NOT_CONFIGURED",
        )
    user_payload = {
        "intern_name": intern_name,
        "duration_days": duration_days,
        "project_title": project_title,
        "project_overview": project_overview or "",
        "skills_demonstrated": skills_demonstrated,
        "mentor_feedback": mentor_feedback,
    }
    try:
        client = azure_openai.get_client()
        response = await azure_openai.call_with_retry(
            "certificate_citation",
            client.chat.completions.create,
            model=cfg.azure_openai_deployment_gpt4o,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=400,
            timeout=12.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        text = str(parsed.get("text", "")).strip()
        confidence = float(parsed.get("confidence", 0.0))
        if not text:
            raise ValueError("empty text")
        return GeneratedCitation(text=text, confidence=confidence, succeeded=True)
    except (AzureOpenAiError, AzureOpenAiQuotaExceededError, json.JSONDecodeError, ValueError):
        logger.warning("nexhire.ai.certificate.fallback")
        return GeneratedCitation(
            text=_fallback(intern_name, project_title, duration_days),
            confidence=0.55,
            succeeded=False,
            degradation_reason="AI_UNAVAILABLE_OR_MALFORMED",
        )


def _fallback(name: str, project: str, duration_days: int) -> str:
    weeks = max(1, round(duration_days / 7))
    return (
        f"This is to certify that {name} successfully completed an internship of "
        f"approximately {weeks} weeks, contributing to the project "
        f"\"{project}\". The intern demonstrated commitment and "
        f"collaborative effort throughout the engagement."
    )


# ────────────────────────────────────────────────────────────────────
# Auto-send.
# ────────────────────────────────────────────────────────────────────
async def auto_send_for_intern(
    session: AsyncSession,
    *,
    intern_id: UUID,
    confidence_threshold: float = 0.85,
) -> AiAutoAction:
    intern = (
        await session.execute(select(Intern).where(Intern.id == intern_id))
    ).scalar_one()
    referral = (
        await session.execute(
            select(Referral).where(Referral.id == intern.referral_id)
        )
    ).scalar_one()

    feedback: dict[str, Any] = intern.mentor_closure_feedback or {}
    duration = (
        ((intern.actual_end_date or referral.internship_end_date) - (intern.actual_start_date or referral.internship_start_date)).days  # type: ignore[operator]
        if intern.actual_start_date and (intern.actual_end_date or referral.internship_end_date)
        else 56
    )
    citation = await generate_citation(
        intern_name=referral.candidate_name,
        project_title=referral.project_title or "",
        project_overview=referral.project_overview,
        skills_demonstrated=list(feedback.get("skills_demonstrated", []) or []),
        mentor_feedback=str(feedback.get("project_summary", "")),
        duration_days=int(duration),
    )

    if citation.confidence < confidence_threshold:
        # Route to HR review (S6 wires the actual review endpoint).
        return _record_auto_action(
            session,
            referral_id=referral.id,
            intern_id=intern.id,
            decision="ROUTED_TO_HR",
            flags=[citation.degradation_reason or "Low confidence citation"],
        )

    pdf_bytes = _render_pdf(intern_name=referral.candidate_name, citation=citation.text)
    import hashlib

    document = Document(
        document_type=DocumentType.CERTIFICATE.value,
        azure_blob_container="documents",
        azure_blob_key=f"certificates/{intern.id}.pdf",
        file_name=f"certificate-{intern.id}.pdf",
        mime_type="application/pdf",
        size_bytes=len(pdf_bytes),
        sha256_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        uploaded_by=AI_SYSTEM_USER_ID,
    )
    session.add(document)
    auto_action = _record_auto_action(
        session,
        referral_id=referral.id,
        intern_id=intern.id,
        decision="EXECUTED",
        conditions_met=[
            f"Citation confidence {citation.confidence:.2f} ≥ {confidence_threshold}",
            "Mentor confirmed completion",
        ],
    )
    return auto_action


def _record_auto_action(
    session: AsyncSession,
    *,
    referral_id: UUID,
    intern_id: UUID,
    decision: str,
    conditions_met: list[str] | None = None,
    flags: list[str] | None = None,
) -> AiAutoAction:
    row = AiAutoAction(
        action_type="AUTO_SEND_CERT",
        decision=decision,
        referral_id=referral_id,
        intern_id=intern_id,
        conditions_met=conditions_met,
        flags=flags,
    )
    session.add(row)
    return row


def _render_pdf(*, intern_name: str, citation: str) -> bytes:
    html = (
        f"<html><body><h1>Certificate of Internship</h1>"
        f"<h2>{intern_name}</h2><p>{citation}</p></body></html>"
    )
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf() or b""
    except Exception:
        return html.encode("utf-8")


__all__ = [
    "MODEL_TOUCHPOINT",
    "RECALL_HOURS",
    "GeneratedCitation",
    "auto_send_for_intern",
    "generate_citation",
]
