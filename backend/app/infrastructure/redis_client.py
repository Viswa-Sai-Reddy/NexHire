"""Async Redis client.

Used for:
  * Rate limiting (sliding-window counters, `middleware/rate_limit.py`).
  * Mentor-suggestion cache (AI-2 results, 1h TTL — `ai/mentor_matcher.py`).
  * Scheduler job-lock idempotency (`acquire_lock`, used by APScheduler
    jobs so e.g. the NDA-timeout sweep runs at most once per window
    even with multiple processes).

Refresh tokens are NOT stored here — they live bcrypt-hashed in the
`sessions` table in Postgres (`auth/models.py:Session.refresh_token_hash`).

The client is a module-level singleton; it auto-connects on first use
and reconnects via the underlying `redis.asyncio.Redis` pool.

All keys are prefixed (`nexhire:<env>:`) so multiple environments can
share an instance during early dev without collisions.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import get_settings
from app.shared.exceptions import RedisUnavailableError

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("nexhire.redis")

_client: Redis[str] | None = None


def _build_prefix() -> str:
    cfg = get_settings()
    return f"nexhire:{cfg.nexhire_env}:"


async def get_client() -> Redis[str]:
    """Lazy singleton. Imports `redis` only when first called so the rest
    of the codebase remains import-safe even if Redis is unreachable in
    a unit test environment.
    """
    global _client
    if _client is None:
        from redis.asyncio import Redis

        cfg = get_settings()
        _client = Redis.from_url(
            cfg.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info("nexhire.redis.connected")
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()  # type: ignore[attr-defined]
        _client = None


def k(*parts: str) -> str:
    """Build a namespaced key. Joins with `:` and prefixes the env."""
    return _build_prefix() + ":".join(parts)


async def healthcheck() -> dict[str, str]:
    try:
        client = await get_client()
        pong = await client.ping()
        return {"status": "ok" if pong else "down"}
    except Exception as exc:
        logger.warning("nexhire.redis.healthcheck_failed", exc_info=exc)
        return {"status": "down", "error": exc.__class__.__name__}


async def acquire_lock(key: str, ttl_seconds: int) -> bool:
    """Set-if-not-exists with TTL. Returns True if the lock was acquired.

    Used by the scheduler to enforce idempotency on time-window jobs
    (e.g. `nda_timeout:2026-05-04` runs at most once per day).
    """
    try:
        client = await get_client()
        result = await client.set(k("lock", key), "1", ex=ttl_seconds, nx=True)
        return bool(result)
    except Exception as exc:
        # Caller (scheduler wrapper) logs a single one-liner; no traceback
        # here so a flapping cache doesn't flood logs.
        logger.debug("nexhire.redis.lock_failed", extra={"key": key}, exc_info=exc)
        raise RedisUnavailableError() from exc
