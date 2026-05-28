# """Gmail API send wrapper.

# Uses a service account with domain-wide delegation per Blueprint §8.
# The send-as alias is `nexhire-noreply@<domain>` (configured in Workspace
# admin). All sends are logged to the `notifications` table with a SHA-256
# of the body — never the full body — to keep PII out of operational logs.

# Dev mode (no `GMAIL_SERVICE_ACCOUNT_JSON_PATH`): callers receive a fake
# message id and the email is logged with a redacted recipient. The real
# send activates the moment credentials are configured.
# """
# from __future__ import annotations

# import asyncio
# import base64
# import hashlib
# import logging
# from email.mime.multipart import MIMEMultipart
# from email.mime.text import MIMEText
# from functools import lru_cache
# from typing import TYPE_CHECKING

# from app.config import get_settings
# from app.shared.exceptions import GmailApiError

# if TYPE_CHECKING:
#     from googleapiclient.discovery import Resource

# logger = logging.getLogger("nexhire.gmail")


# @lru_cache(maxsize=1)
# def get_service() -> Resource:
#     from google.oauth2 import service_account
#     from googleapiclient.discovery import build

#     cfg = get_settings()
#     if not cfg.gmail_service_account_json_path:
#         raise RuntimeError("GMAIL_SERVICE_ACCOUNT_JSON_PATH is not configured")

#     creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
#         cfg.gmail_service_account_json_path,
#         scopes=["https://www.googleapis.com/auth/gmail.send"],
#     )
#     delegated = creds.with_subject(cfg.gmail_domain_delegated_user)
#     return build("gmail", "v1", credentials=delegated, cache_discovery=False)


# def is_configured() -> bool:
#     """True iff at least one send path has credentials wired up."""
#     cfg = get_settings()
#     if not cfg.gmail_sender_email:
#         return False
#     return bool(cfg.gmail_app_password or cfg.gmail_service_account_json_path)


# def _use_smtp() -> bool:
#     """Prefer SMTP over service-account when both are available — App
#     Passwords work with personal Gmail; domain-wide delegation needs
#     Workspace.
#     """
#     return bool(get_settings().gmail_app_password)


# async def send_html(
#     *,
#     to: str,
#     subject: str,
#     html_body: str,
#     plain_fallback: str | None = None,
# ) -> str:
#     """Send a multipart email and return a message identifier.

#     Dev mode (no creds) returns a deterministic fake message id so the
#     rest of the pipeline still exercises end-to-end without touching
#     Gmail.
#     """
#     cfg = get_settings()
#     if not is_configured():
#         logger.info(
#             "nexhire.gmail.dev_send",
#             extra={"to_domain": _redact_email(to), "subject": subject[:80]},
#         )
#         return f"dev-{hashlib.sha256(html_body.encode()).hexdigest()[:16]}"

#     if _use_smtp():
#         try:
#             return await asyncio.to_thread(
#                 _send_via_smtp,
#                 to=to,
#                 subject=subject,
#                 sender=cfg.gmail_sender_email,
#                 app_password=cfg.gmail_app_password,
#                 html=html_body,
#                 plain=plain_fallback,
#             )
#         except Exception as exc:
#             logger.exception("nexhire.gmail.smtp_send_failed")
#             raise GmailApiError() from exc

#     body = build_mime(
#         to=to,
#         subject=subject,
#         sender=cfg.gmail_sender_email,
#         html=html_body,
#         plain=plain_fallback,
#     )

#     def _send_blocking() -> str:
#         service = get_service()
#         result = (
#             service.users()
#             .messages()
#             .send(userId="me", body={"raw": body})
#             .execute()
#         )
#         return str(result.get("id", ""))

#     try:
#         return await asyncio.to_thread(_send_blocking)
#     except Exception as exc:
#         logger.exception("nexhire.gmail.send_failed")
#         raise GmailApiError() from exc


# def _send_via_smtp(
#     *,
#     to: str,
#     subject: str,
#     sender: str,
#     app_password: str,
#     html: str,
#     plain: str | None,
# ) -> str:
#     """Send via Gmail SMTP using an App Password. Synchronous; called
#     from `asyncio.to_thread` in `send_html`.
#     """
#     import smtplib
#     from email.utils import make_msgid

#     msg = MIMEMultipart("alternative")
#     msg["From"] = sender
#     msg["To"] = to
#     msg["Subject"] = subject
#     msg["Message-ID"] = make_msgid(domain="nexhire")
#     if plain:
#         msg.attach(MIMEText(plain, "plain", "utf-8"))
#     msg.attach(MIMEText(html, "html", "utf-8"))

#     # App Passwords are displayed with spaces for readability; Google
#     # accepts either form, but stripping spaces guards against copy-paste
#     # quirks.
#     cleaned_password = app_password.replace(" ", "")

#     with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
#         server.ehlo()
#         server.starttls()
#         server.ehlo()
#         server.login(sender, cleaned_password)
#         server.send_message(msg)
#     return msg["Message-ID"] or "smtp-sent"


# def build_mime(
#     *,
#     to: str,
#     subject: str,
#     sender: str,
#     html: str,
#     plain: str | None,
# ) -> str:
#     """Construct an RFC 822 multipart message and return the base64url
#     blob the Gmail API expects in `users.messages.send`.
#     """
#     msg = MIMEMultipart("alternative")
#     msg["From"] = sender
#     msg["To"] = to
#     msg["Subject"] = subject
#     if plain:
#         msg.attach(MIMEText(plain, "plain", "utf-8"))
#     msg.attach(MIMEText(html, "html", "utf-8"))
#     return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


# def _redact_email(email: str) -> str:
#     """Log-safe form: keep the domain, hash the local part."""
#     if "@" not in email:
#         return "<invalid>"
#     local, domain = email.rsplit("@", 1)
#     digest = hashlib.sha256(local.encode("utf-8")).hexdigest()[:8]
#     return f"{digest}@{domain}"


# # Re-export for typed catch in callers
# GmailError = GmailApiError


# __all__ = ["GmailError", "build_mime", "get_service", "is_configured", "send_html"]


from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import pickle
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache
from typing import TYPE_CHECKING

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import get_settings
from app.shared.exceptions import GmailApiError

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource

logger = logging.getLogger("nexhire.gmail")

TOKEN_PATH = r".secret/gmail_token.pkl"


@lru_cache(maxsize=1)
def get_service() -> "Resource":
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "gmail_token.pkl not found. Run generate_token.py first."
        )

    with open(TOKEN_PATH, "rb") as f:
        creds = pickle.load(f)

    if creds.expired and creds.refresh_token:
        logger.info("nexhire.gmail.token_refresh")
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)
        # Clear cache so next call gets fresh service
        get_service.cache_clear()

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def is_configured() -> bool:
    """True iff gmail_token.pkl exists and sender email is set."""
    cfg = get_settings()
    if not cfg.gmail_sender_email:
        return False
    return os.path.exists(TOKEN_PATH)


async def send_html(
    *,
    to: str,
    subject: str,
    html_body: str,
    plain_fallback: str | None = None,
) -> str:
    """Send a multipart email and return a message identifier.

    Dev mode (no creds) returns a deterministic fake message id so the
    rest of the pipeline still exercises end-to-end without touching
    Gmail.
    """
    cfg = get_settings()

    if not is_configured():
        logger.info(
            "nexhire.gmail.dev_send",
            extra={"to_domain": _redact_email(to), "subject": subject[:80]},
        )
        return f"dev-{hashlib.sha256(html_body.encode()).hexdigest()[:16]}"

    body = build_mime(
        to=to,
        subject=subject,
        sender=cfg.gmail_sender_email,
        html=html_body,
        plain=plain_fallback,
    )

    def _send_blocking() -> str:
        service = get_service()
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": body})
            .execute()
        )
        return str(result.get("id", ""))

    try:
        return await asyncio.to_thread(_send_blocking)
    except Exception as exc:
        logger.exception("nexhire.gmail.send_failed")
        raise GmailApiError() from exc


def build_mime(
    *,
    to: str,
    subject: str,
    sender: str,
    html: str,
    plain: str | None = None,
) -> str:
    """Construct an RFC 822 multipart message and return the base64url
    blob the Gmail API expects in `users.messages.send`.
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if plain:
        msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii") 
def _redact_email(email: str) -> str:
    """Log-safe form: keep the domain, hash the local part."""
    if "@" not in email:
        return "<invalid>"
    local, domain = email.rsplit("@", 1)
    digest = hashlib.sha256(local.encode("utf-8")).hexdigest()[:8]
    return f"{digest}@{domain}"


# Re-export for typed catch in callers
GmailError = GmailApiError

__all__ = ["GmailError", "build_mime", "get_service", "is_configured", "send_html"]