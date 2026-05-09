"""Redis-backed rate limiter.

Token-bucket-ish using a 60-second sliding window via fixed-window
counters. Cheap, predictable, good enough for v1.

Per-role + per-bucket limits live in settings. The dependency takes
a *bucket name* so different endpoint groups can have different
limits ("default", "ai", "unauth").

Failure mode: if Redis is down, we fail OPEN (let the request through).
This is a deliberate trade-off — the audit / business-rule layers are
the real guards. Rate limiting is for protection against abuse and
should not become a downtime amplifier.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import Request

from app.config import get_settings
from app.infrastructure import redis_client
from app.shared.exceptions import NexHireBaseException

logger = logging.getLogger("nexhire.rate_limit")

Bucket = Literal["default", "ai", "unauth"]


class RateLimitExceededError(NexHireBaseException):
    code = "RATE_LIMIT_EXCEEDED"
    user_message = "Too many requests. Please slow down and try again shortly."


def _limit_for(bucket: Bucket) -> int:
    cfg = get_settings()
    return {
        "default": cfg.rate_limit_per_minute_default,
        "ai": cfg.rate_limit_per_minute_ai,
        "unauth": cfg.rate_limit_per_minute_unauth,
    }[bucket]


def _key_for(bucket: Bucket, identifier: str) -> str:
    # Window is per UTC minute — clients see resets at :00.
    import time

    minute_bucket = int(time.time() // 60)
    return redis_client.k("rl", bucket, identifier, str(minute_bucket))


async def _identifier(request: Request) -> str:
    """Pick the most-specific identifier we have. Falls back to IP."""
    # Set by `auth.get_current_user` via context var.
    from app.middleware.logging import actor_user_id_ctx

    actor = actor_user_id_ctx.get()
    if actor:
        return f"u:{actor}"
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return f"ip:{forwarded or (request.client.host if request.client else 'unknown')}"


def rate_limit(bucket: Bucket = "default"):  # type: ignore[no-untyped-def]
    """Build a FastAPI dependency that enforces `bucket`'s limit.

    Usage:
        @router.post("/foo", dependencies=[Depends(rate_limit("ai"))])
    """

    async def dependency(request: Request) -> None:
        try:
            identifier = await _identifier(request)
            client = await redis_client.get_client()
            key = _key_for(bucket, identifier)
            count = await client.incr(key)
            if count == 1:
                # First hit in this minute — set the expiry.
                await client.expire(key, 60)
            limit = _limit_for(bucket)
            if count > limit:
                raise RateLimitExceededError(
                    details={"bucket": bucket, "limit_per_minute": limit},
                )
        except RateLimitExceededError:
            raise
        except Exception as exc:
            logger.warning(
                "nexhire.rate_limit.degraded",
                extra={"bucket": bucket, "error": exc.__class__.__name__},
            )

    return dependency
