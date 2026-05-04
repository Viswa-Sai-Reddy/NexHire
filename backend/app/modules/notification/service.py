"""Notification service — send + persist + retry handoff.

Public API:
  * `send_template(session, template_id, recipient, context, *,
                    referral_id=None, ...)`
    Renders the template, sends via Gmail, writes a `notifications` row.
    Failures persist a `status=FAILED` row with `last_error`; the retry
    job (S1+) picks them up.

The body itself is **never** stored — only the SHA-256. Subject + a
hash digest are sufficient for diagnostics; PII never lands in the
operational logs (Blueprint §8 + GDPR-style minimization).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.notification import template_renderer
from app.modules.referral.models import Notification, NotificationTemplate
from app.shared.exceptions import GmailApiError

logger = logging.getLogger("nexhire.notification")


async def send_template(
    session: AsyncSession,
    *,
    template_id: str,
    recipient: str,
    context: dict[str, Any],
    referral_id: UUID | None = None,
    template_filename: str | None = None,
) -> Notification:
    """Render + send + persist.

    The `template_filename` is the Jinja file (without `.html`); it
    defaults to the lowercase tail of `template_id`. The `subject` line
    is read from `notification_templates.subject` (seeded at install)
    so wording can be tweaked without a deploy.
    """
    template_row = (
        await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.template_id == template_id,
                NotificationTemplate.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if template_row is None:
        raise GmailApiError(
            user_message=f"Notification template {template_id!r} is not configured.",
        )

    file_stem = template_filename or _filename_for(template_id)
    rendered = template_renderer.render(
        file_stem,
        subject=template_row.subject,
        context=context,
    )

    body_hash = hashlib.sha256(rendered.html.encode("utf-8")).hexdigest()

    notification = Notification(
        template_id=template_id,
        recipient_email=recipient,
        subject=rendered.subject,
        body_sha256=body_hash,
        referral_id=referral_id,
        status="QUEUED",
    )
    session.add(notification)
    await session.flush()

    try:
        message_id = await _gmail_send(
            to=recipient,
            subject=rendered.subject,
            html=rendered.html,
            plain=rendered.plain,
        )
        notification.gmail_message_id = message_id
        notification.status = "SENT"
        from datetime import datetime, timezone

        notification.sent_at = datetime.now(timezone.utc)
    except Exception as exc:
        # Don't crash the surrounding transaction. The retry worker
        # will pick this up; the row stays at FAILED.
        notification.status = "FAILED"
        notification.last_error = str(exc)[:1_000]
        logger.warning(
            "nexhire.notification.send_failed",
            extra={
                "template_id": template_id,
                "recipient_domain": _redact_email(recipient),
                "error": exc.__class__.__name__,
            },
        )

    return notification


# ────────────────────────────────────────────────────────────────────
# Gmail send — wraps the synchronous googleapiclient via to_thread.
# Real implementation lands when GMAIL credentials are available; in
# dev the env-var GMAIL_SERVICE_ACCOUNT_JSON_PATH is empty and we
# log + return a fake message id so the rest of the pipeline still
# exercises end-to-end.
# ────────────────────────────────────────────────────────────────────
async def _gmail_send(
    *, to: str, subject: str, html: str, plain: str | None
) -> str:
    cfg = get_settings()
    if not cfg.gmail_service_account_json_path or not cfg.gmail_sender_email:
        logger.info(
            "nexhire.notification.dev_send",
            extra={"to_domain": _redact_email(to), "subject": subject[:80]},
        )
        return f"dev-{hashlib.sha1(html.encode()).hexdigest()[:16]}"

    from app.infrastructure import gmail_client

    def _send_blocking() -> str:
        service = gmail_client.get_service()
        body = gmail_client._build_mime(  # noqa: SLF001 — internal helper
            to=to,
            subject=subject,
            sender=cfg.gmail_sender_email,
            html=html,
            plain=plain,
        )
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": body})
            .execute()
        )
        return str(result.get("id", ""))

    try:
        return await asyncio.to_thread(_send_blocking)
    except Exception as exc:  # noqa: BLE001 — preserve original cause
        logger.exception("nexhire.notification.gmail_failed")
        raise GmailApiError() from exc


def _filename_for(template_id: str) -> str:
    """Map `NOTIF_002_MENTOR_ASSIGNMENT` → `mentor_assignment`."""
    parts = template_id.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:]).lower()
    return template_id.lower()


def _redact_email(email: str) -> str:
    """Log-safe form: keep the domain, hash the local part."""
    if "@" not in email:
        return "<invalid>"
    local, domain = email.rsplit("@", 1)
    digest = hashlib.sha256(local.encode("utf-8")).hexdigest()[:8]
    return f"{digest}@{domain}"


__all__ = ["send_template"]
