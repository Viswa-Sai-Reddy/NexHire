"""Structured logging configuration + request-ID propagation.

We use the stdlib `logging` module (not structlog as a hard dep) and
emit JSON via `structlog` only in production. In dev we emit a
human-readable line. Either way, every log record carries:

  * `request_id`     — uuid4 per inbound HTTP request
  * `actor_user_id`  — set after JWT auth resolves the user
  * `correlation_id` — set when a domain event triggers downstream work

Request IDs are surfaced to clients in the `X-Request-Id` response
header and embedded in error envelopes (Blueprint §17.2).
"""
from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config import get_settings

# ────────────────────────────────────────────────────────────────────
# Context vars — read by structlog processors and audit publisher.
# ────────────────────────────────────────────────────────────────────
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
actor_user_id_ctx: ContextVar[str | None] = ContextVar("actor_user_id", default=None)
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def configure_logging() -> None:
    """Wire stdlib logging + structlog. Call once at startup."""
    cfg = get_settings()
    level = getattr(logging, cfg.nexhire_log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_request_context,
    ]

    if cfg.is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[*shared_processors, renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    # stdlib root → stderr, plain (App Insights ingests structured payloads
    # via the OpenCensus exporter wired by the observability slice).
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _add_request_context(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Merge request_id / actor / correlation_id into every log record."""
    rid = request_id_ctx.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    aid = actor_user_id_ctx.get()
    if aid:
        event_dict.setdefault("actor_user_id", aid)
    cid = correlation_id_ctx.get()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


# ────────────────────────────────────────────────────────────────────
# Middleware: assigns a request_id and exposes it on the response.
# ────────────────────────────────────────────────────────────────────
REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generates / propagates `X-Request-Id`.

    Honors a client-supplied ID (must be a UUID) so distributed traces
    upstream of NexHire can correlate. If the header is missing or
    malformed we generate a fresh UUID.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if _looks_like_uuid(incoming) else str(uuid.uuid4())

        token = request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers[REQUEST_ID_HEADER] = rid
        return response


def _looks_like_uuid(value: str) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def get_logger(name: str = "nexhire") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
