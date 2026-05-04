"""Gmail API send wrapper.

S0 ships the shape; S1 fills in template rendering + delivery tracking.

Uses a service account with domain-wide delegation per Blueprint §8.
The send-as alias is `nexhire-noreply@<domain>` (configured in Workspace
admin). All sends are logged to the `notifications` table with a SHA-256
of the body — never the full body — to keep PII out of operational logs.
"""
from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings
from app.shared.exceptions import GmailApiError

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource

logger = logging.getLogger("nexhire.gmail")


@lru_cache(maxsize=1)
def get_service() -> "Resource":
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    cfg = get_settings()
    if not cfg.gmail_service_account_json_path:
        raise RuntimeError("GMAIL_SERVICE_ACCOUNT_JSON_PATH is not configured")

    creds = service_account.Credentials.from_service_account_file(
        cfg.gmail_service_account_json_path,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    delegated = creds.with_subject(cfg.gmail_domain_delegated_user)
    return build("gmail", "v1", credentials=delegated, cache_discovery=False)


async def send_html(
    *,
    to: str,
    subject: str,
    html_body: str,
    plain_fallback: str | None = None,
) -> str:
    """Send a multipart email and return the Gmail message ID.

    NOTE: googleapiclient is sync — wrap in `asyncio.to_thread` for the
    real impl in S1 to avoid blocking the loop. The placeholder below
    raises if called pre-S1 to surface accidental usage.
    """
    raise NotImplementedError(
        "Gmail send is wired in S1 (notification module). The shape is locked here."
    )


def _build_mime(
    *,
    to: str,
    subject: str,
    sender: str,
    html: str,
    plain: str | None,
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


# Re-export for typed catch in callers
GmailError = GmailApiError
