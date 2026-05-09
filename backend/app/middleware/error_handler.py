"""Global FastAPI exception handlers.

Direct implementation of Blueprint §17.4. Every error from the API
returns the same envelope:

    {
      "error": {
        "code":      "<stable machine code>",
        "category":  "VALIDATION_ERROR | AUTH_ERROR | BUSINESS_RULE_ERROR
                      | INTEGRATION_ERROR | SYSTEM_ERROR",
        "message":   "<safe-to-display human message>",
        "details":   { ... },
        "request_id": "<from X-Request-Id>",
        "timestamp": "<UTC ISO-8601>"
      }
    }

Behaviour:
  * `BusinessRuleError` is *also* written to `audit_events` so attempted
    rule violations are auditable (Blueprint §17.4 last paragraph).
  * `IntegrityError` is mapped to a domain error via
    `database.map_integrity_error` so unique-constraint hits surface
    cleanly to the user (e.g. DUPLICATE_CANDIDATE_BLOCKED).
  * Unhandled exceptions emit a generic 500 with the request_id; full
    stack traces only go to App Insights, never the response body.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database import map_integrity_error
from app.middleware.logging import request_id_ctx
from app.shared.exceptions import (
    AuthError,
    BusinessRuleError,
    IntegrationError,
    NexHireBaseException,
    ValidationError,
)
from app.shared.exceptions import (
    SystemError as NexHireSystemError,
)

logger = logging.getLogger("nexhire.errors")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _envelope(
    *,
    code: str,
    category: str,
    message: str,
    details: dict[str, Any] | None = None,
    docs_url: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "category": category,
            "message": message,
            "details": details or {},
            "request_id": request_id_ctx.get(),
            "timestamp": _now_iso(),
        }
    }
    if docs_url:
        body["error"]["docs_url"] = docs_url
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler. Call once during app construction."""

    @app.exception_handler(ValidationError)
    async def _validation(request: Request, exc: ValidationError) -> JSONResponse:
        logger.warning(
            "nexhire.error.validation",
            extra={"code": exc.code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=400,
            content=_envelope(
                code=exc.code,
                category="VALIDATION_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic / FastAPI validation. We unify under a single
        # MISSING_MANDATORY_FIELD code unless the failure is more specific.
        first_error = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first_error.get("loc", ()))
        msg = first_error.get("msg", "Invalid input.")
        logger.warning(
            "nexhire.error.pydantic",
            extra={"path": request.url.path, "field": loc, "detail": msg},
        )
        return JSONResponse(
            status_code=400,
            content=_envelope(
                code="MISSING_MANDATORY_FIELD",
                category="VALIDATION_ERROR",
                message=msg,
                details={"field": loc, "errors": exc.errors()},
            ),
        )

    @app.exception_handler(AuthError)
    async def _auth(request: Request, exc: AuthError) -> JSONResponse:
        # 401 vs 403: permission-class errors → 403, anything else → 401.
        status = 403 if exc.code == "INSUFFICIENT_PERMISSIONS" else 401
        logger.warning(
            "nexhire.error.auth",
            extra={"code": exc.code, "path": request.url.path, "status": status},
        )
        return JSONResponse(
            status_code=status,
            content=_envelope(
                code=exc.code,
                category="AUTH_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(BusinessRuleError)
    async def _business_rule(request: Request, exc: BusinessRuleError) -> JSONResponse:
        logger.warning(
            "nexhire.error.business_rule",
            extra={
                "code": exc.code,
                "rule_id": exc.rule_id,
                "path": request.url.path,
            },
        )
        # Audit publish — see Blueprint §17.4 ("every business rule
        # violation is also an audit event"). We import lazily to avoid
        # an import cycle since audit.py also needs error handling.
        try:
            from app.middleware.audit import audit_business_rule_violation

            await audit_business_rule_violation(exc, path=request.url.path)
        except Exception:
            logger.exception("nexhire.error.audit_publish_failed")

        return JSONResponse(
            status_code=422,
            content=_envelope(
                code=exc.code,
                category="BUSINESS_RULE_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(IntegrationError)
    async def _integration(request: Request, exc: IntegrationError) -> JSONResponse:
        # 503 for "down right now, retry later"; 502 for "bad reply from
        # upstream". Default to 502 unless the exception explicitly opts
        # for 503 (none currently — placeholder for future expansion).
        status = 502
        logger.error(
            "nexhire.error.integration",
            extra={
                "code": exc.code,
                "service": exc.service,
                "path": request.url.path,
            },
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status,
            content=_envelope(
                code=exc.code,
                category="INTEGRATION_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        # Map known constraints to domain errors.
        mapped = map_integrity_error(exc)
        if isinstance(mapped, BusinessRuleError):
            return await _business_rule(request, mapped)
        # Unmapped: treat as system error so an alert fires.
        logger.exception(
            "nexhire.error.unmapped_integrity",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                code="UNEXPECTED_ERROR",
                category="SYSTEM_ERROR",
                message="A data conflict occurred. Please contact support.",
            ),
        )

    @app.exception_handler(NexHireSystemError)
    async def _system(request: Request, exc: NexHireSystemError) -> JSONResponse:
        logger.exception(
            "nexhire.error.system",
            extra={"code": exc.code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                code=exc.code,
                category="SYSTEM_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(NexHireBaseException)
    async def _base(request: Request, exc: NexHireBaseException) -> JSONResponse:
        # Catches any subclass we somehow forgot to register above.
        logger.exception(
            "nexhire.error.base_fallback",
            extra={"code": exc.code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                code=exc.code,
                category="SYSTEM_ERROR",
                message=exc.user_message,
                details=exc.details,
            ),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "nexhire.error.unexpected",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                code="UNEXPECTED_ERROR",
                category="SYSTEM_ERROR",
                message=(
                    "Something went wrong on our end. "
                    "Our team has been notified. Please try again in a moment."
                ),
            ),
        )
