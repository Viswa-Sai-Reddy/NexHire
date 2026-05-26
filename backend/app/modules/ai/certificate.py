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
from datetime import date
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

    # Mentor name for the signature line.
    from app.modules.auth.models import User

    mentor = (
        await session.execute(select(User).where(User.id == referral.mentor_id))
    ).scalar_one_or_none()
    mentor_name = mentor.full_name if mentor and mentor.full_name else "Program Mentor"

    # Issue date: end of internship preferred, falls back to today.
    issue_date = (
        intern.actual_end_date or referral.internship_end_date or date.today()
    )

    pdf_bytes = _render_pdf(
        intern_name=referral.candidate_name,
        citation=citation.text,
        mentor_name=mentor_name,
        issue_date=issue_date,
        project_title=referral.project_title,
    )
    import hashlib

    from app.infrastructure import azure_blob

    blob_key = f"certificates/{intern.id}.pdf"
    file_name = f"certificate-{intern.id}.pdf"
    # Upload the bytes BEFORE recording the Document row — otherwise the
    # SAS download URL points at a blob that never landed in storage.
    await azure_blob.upload(
        container="documents",
        data=pdf_bytes,
        content_type="application/pdf",
        filename=file_name,
        blob_key=blob_key,
        overwrite=True,
    )

    document = Document(
        document_type=DocumentType.CERTIFICATE.value,
        azure_blob_container="documents",
        azure_blob_key=blob_key,
        file_name=file_name,
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


BRAND_NAME = "HEXAWARE"

# Cached state for the optional script signature font. Registered once
# on first render; falls back to a built-in italic if the TTF isn't
# present in `backend/app/modules/ai/fonts/`.
_SIG_FONT_CACHE: dict[str, str | bool] = {}


def _register_signature_font() -> str:
    """Try to register a script font for the mentor signature.

    Looks for any of these TTF/OTF files under `app/modules/ai/fonts/`
    (in priority order). Returns the font name to pass to
    `Canvas.setFont(...)`. If no file is found, returns the built-in
    `Times-BoldItalic` so the certificate still renders.

    Drop `Silentha-Regular.ttf` into that directory (or any of the other
    candidate names below) to activate the script signature.
    """
    if _SIG_FONT_CACHE.get("done"):
        return str(_SIG_FONT_CACHE["name"])

    from pathlib import Path

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    candidates = [
        ("Silentha", "Silentha-Regular.ttf"),
        ("Silentha", "Silentha Regular.ttf"),
        ("Silentha", "silentha-regular.ttf"),
        ("Silentha", "silentha.regular.ttf"),
        ("Silentha", "Silentha.Regular.ttf"),
        ("Allura", "Allura-Regular.ttf"),
        ("GreatVibes", "GreatVibes-Regular.ttf"),
        ("Sacramento", "Sacramento-Regular.ttf"),
        ("DancingScript", "DancingScript-Regular.ttf"),
    ]
    for name, filename in candidates:
        path = fonts_dir / filename
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
                _SIG_FONT_CACHE["done"] = True
                _SIG_FONT_CACHE["name"] = name
                logger.info(
                    "nexhire.ai.certificate.signature_font_loaded",
                    extra={"font": name, "path": str(path)},
                )
                return name
            except Exception:
                logger.exception(
                    "nexhire.ai.certificate.font_register_failed",
                    extra={"path": str(path)},
                )

    _SIG_FONT_CACHE["done"] = True
    _SIG_FONT_CACHE["name"] = "Times-BoldItalic"
    return "Times-BoldItalic"


def _render_pdf(
    *,
    intern_name: str,
    citation: str,
    mentor_name: str,
    issue_date: date,  # type: ignore[name-defined]
    project_title: str | None = None,
) -> bytes:
    # WeasyPrint (when installed) renders the HTML version below.
    # Otherwise, use ReportLab Canvas to draw the landscape certificate.
    html = _render_html(
        intern_name=intern_name,
        citation=citation,
        mentor_name=mentor_name,
        issue_date=issue_date,
        project_title=project_title,
    )
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]

        pdf = HTML(string=html).write_pdf()
        if pdf:
            return pdf
    except Exception:
        pass

    try:
        return _render_pdf_reportlab(
            intern_name=intern_name,
            citation=citation,
            mentor_name=mentor_name,
            issue_date=issue_date,
        )
    except Exception:
        logger.exception("nexhire.ai.certificate.render_failed")
        return html.encode("utf-8")


def _render_pdf_reportlab(
    *,
    intern_name: str,
    citation: str,
    mentor_name: str,
    issue_date: date,  # type: ignore[name-defined]
) -> bytes:
    """Draw a landscape A4 certificate with Hexaware branding using a
    Canvas. Pixel-positioned for predictable layout across hosts.
    """
    from io import BytesIO

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    page_w, page_h = landscape(A4)  # 842 x 595 pt
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # Colors — dark navy for text, gold for borders/accents.
    navy = (0.09, 0.13, 0.27)
    gold = (0.72, 0.55, 0.13)
    body = (0.18, 0.18, 0.18)

    # Outer + inner double border for the "framed" feel.
    c.setStrokeColorRGB(*gold)
    c.setLineWidth(4)
    c.rect(28, 28, page_w - 56, page_h - 56)
    c.setLineWidth(0.6)
    c.rect(38, 38, page_w - 76, page_h - 76)

    # Top band: brand centered, flanked by gold diamond accents.
    brand_font, brand_size = "Helvetica-Bold", 26
    brand_y = page_h - 85
    brand_w = stringWidth(BRAND_NAME, brand_font, brand_size)
    c.setFillColorRGB(*navy)
    c.setFont(brand_font, brand_size)
    c.drawCentredString(page_w / 2, brand_y, BRAND_NAME)

    c.setFillColorRGB(*gold)
    c.setFont("Helvetica", 16)
    diamond_offset = brand_w / 2 + 18
    c.drawString(page_w / 2 + diamond_offset, brand_y + 2, "♦")
    c.drawRightString(page_w / 2 - diamond_offset, brand_y + 2, "♦")

    # Horizontal rule under the brand band.
    c.setStrokeColorRGB(*gold)
    c.setLineWidth(0.8)
    c.line(60, page_h - 105, page_w - 60, page_h - 105)

    # Title.
    c.setFillColorRGB(*navy)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(page_w / 2, page_h - 150, "CERTIFICATE OF INTERNSHIP")

    # Intro line.
    c.setFillColorRGB(*body)
    c.setFont("Helvetica", 12)
    c.drawCentredString(page_w / 2, page_h - 190, "This is to certify that")

    # Intern name — italic for elegance, with a thin underline.
    c.setFillColorRGB(*navy)
    c.setFont("Times-Italic", 26)
    c.drawCentredString(page_w / 2, page_h - 230, intern_name)
    name_w = stringWidth(intern_name, "Times-Italic", 26)
    rule_half = max(name_w / 2 + 24, 160)
    c.setStrokeColorRGB(*gold)
    c.setLineWidth(0.8)
    c.line(page_w / 2 - rule_half, page_h - 245, page_w / 2 + rule_half, page_h - 245)

    # Citation paragraph (wrapped, centered).
    c.setFillColorRGB(*body)
    c.setFont("Times-Roman", 12)
    inner_max = page_w - 160  # 80pt margin each side
    lines = _wrap_text(citation, "Times-Roman", 12, inner_max)
    y = page_h - 285
    for ln in lines:
        c.drawCentredString(page_w / 2, y, ln)
        y -= 16

    # Footer: mentor signature (left) and issue date (right).
    # Layout is signature/value ABOVE the rule, label BELOW — so the
    # mentor's name reads like a hand-signed digital signature.
    sig_y = 100
    rule_y = sig_y - 4
    label_y = sig_y - 18

    left_x = 130
    right_x = page_w - 130
    rule_half = 100

    c.setStrokeColorRGB(*body)
    c.setLineWidth(0.6)
    c.line(left_x - rule_half, rule_y, left_x + rule_half, rule_y)
    c.line(right_x - rule_half, rule_y, right_x + rule_half, rule_y)

    # Mentor name as a digital signature — script font (Silentha or a
    # similar TTF dropped into app/modules/ai/fonts/) in deep
    # signature-blue. Falls back to Times-BoldItalic when no TTF is
    # present. Script fonts read smaller for their nominal size, so the
    # script path bumps the size up.
    sig_blue = (0.05, 0.32, 0.62)
    sig_font = _register_signature_font()
    sig_size = 32 if sig_font != "Times-BoldItalic" else 20
    c.setFillColorRGB(*sig_blue)
    c.setFont(sig_font, sig_size)
    c.drawCentredString(left_x, sig_y + 6, mentor_name)

    # Issue date stays plain.
    c.setFillColorRGB(*navy)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(right_x, sig_y + 6, _format_date(issue_date))

    c.setFillColorRGB(*body)
    c.setFont("Helvetica", 9)
    c.drawCentredString(left_x, label_y, "Mentor (digitally signed)")
    c.drawCentredString(right_x, label_y, "Date of issue")

    c.showPage()
    c.save()
    return buf.getvalue()


def _wrap_text(text: str, font: str, size: int, max_width: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _format_date(d: date) -> str:  # type: ignore[name-defined]
    # e.g. "September 26, 2026"
    return d.strftime("%B %d, %Y")


def _render_html(
    *,
    intern_name: str,
    citation: str,
    mentor_name: str,
    issue_date: date,  # type: ignore[name-defined]
    project_title: str | None,  # noqa: ARG001 — accepted for future template use
) -> str:
    return (
        f"<html><body>"
        f"<h1>Certificate of Internship</h1>"
        f"<p>{BRAND_NAME}</p>"
        f"<p>This is to certify that</p>"
        f"<h2><em>{intern_name}</em></h2>"
        f"<p>{citation}</p>"
        f"<p><strong>{mentor_name}</strong> &middot; Mentor</p>"
        f"<p>{_format_date(issue_date)} &middot; Date of issue</p>"
        f"</body></html>"
    )


__all__ = [
    "MODEL_TOUCHPOINT",
    "RECALL_HOURS",
    "GeneratedCitation",
    "auto_send_for_intern",
    "generate_citation",
]
