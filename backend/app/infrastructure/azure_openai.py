"""Azure OpenAI async client wrapper.

Behaviour locked:
  * Exponential backoff on rate limits (1s, 2s, 4s, 8s) — Blueprint §17.6.
  * Quota-exceeded → AzureOpenAiQuotaExceededError → flows degrade.
  * Cost tracking: every successful call emits a structured log line
    (`nexhire.openai.usage`) with `tokens_total` + `latency_ms` so
    Application Insights / Loki can aggregate. A small in-process ring
    buffer (`recent_usage()`) is exposed for PO dashboards.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.shared.exceptions import (
    AzureOpenAiError,
    AzureOpenAiQuotaExceededError,
    AzureOpenAiRateLimitedError,
)

if TYPE_CHECKING:
    from openai import AsyncAzureOpenAI

logger = logging.getLogger("nexhire.openai")

_RETRY_DELAYS_SECONDS: tuple[float, ...] = (1, 2, 4, 8)


@dataclass(frozen=True, slots=True)
class UsageEvent:
    operation: str
    tokens_total: int | None
    latency_ms: int
    succeeded: bool


# In-process ring buffer of the last 500 calls. Lets the PO dashboard
# fetch a quick snapshot without standing up App Insights for v1.
_USAGE_BUFFER: deque[UsageEvent] = deque(maxlen=500)


def record_usage(
    operation: str,
    *,
    tokens_total: int | None,
    latency_ms: int,
    succeeded: bool,
) -> None:
    """Append a usage event + log structured for downstream aggregators.

    Callers (resume_parser, certificate, etc.) invoke this after each
    successful Azure OpenAI request once they've extracted the token
    count from `response.usage`. `call_with_retry` emits a minimal event
    too, so even callers that don't extract usage produce latency rows.
    """
    event = UsageEvent(
        operation=operation,
        tokens_total=tokens_total,
        latency_ms=latency_ms,
        succeeded=succeeded,
    )
    _USAGE_BUFFER.append(event)
    logger.info(
        "nexhire.openai.usage",
        extra={
            "op": operation,
            "tokens_total": tokens_total,
            "latency_ms": latency_ms,
            "succeeded": succeeded,
        },
    )


def recent_usage(limit: int = 100) -> list[UsageEvent]:
    """Snapshot of the most recent calls, newest first."""
    snap = list(_USAGE_BUFFER)
    snap.reverse()
    return snap[:limit]


@lru_cache(maxsize=1)
def get_client() -> AsyncAzureOpenAI:
    from openai import AsyncAzureOpenAI

    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is not configured")
    return AsyncAzureOpenAI(
        api_key=cfg.azure_openai_api_key,
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.azure_openai_endpoint,
    )


async def call_with_retry[T](
    operation_name: str,
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """Run an OpenAI SDK call with exponential backoff against
    `RateLimitError`. Quota errors re-raise immediately (no retry helps).

    `fn` is the bound coroutine-returning method (e.g.
    `client.chat.completions.create`). Kept untyped — the SDK has many
    differing call signatures and we don't want to over-fit the wrapper.
    """
    from openai import APIError, APITimeoutError, RateLimitError

    last_exc: BaseException | None = None
    for delay in _RETRY_DELAYS_SECONDS:
        started = time.monotonic()
        try:
            result = await fn(*args, **kwargs)
            latency_ms = int((time.monotonic() - started) * 1000)
            tokens = _extract_tokens(result)
            record_usage(
                operation_name,
                tokens_total=tokens,
                latency_ms=latency_ms,
                succeeded=True,
            )
            return result
        except RateLimitError as exc:
            last_exc = exc
            logger.warning(
                "nexhire.openai.rate_limited",
                extra={"op": operation_name, "retry_in_s": delay},
            )
            await asyncio.sleep(delay)
        except APITimeoutError as exc:
            last_exc = exc
            logger.warning(
                "nexhire.openai.timeout",
                extra={"op": operation_name, "retry_in_s": delay},
            )
            await asyncio.sleep(delay)
        except APIError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            record_usage(
                operation_name,
                tokens_total=None,
                latency_ms=latency_ms,
                succeeded=False,
            )
            # 429 quota / 5xx → don't burn the retry budget
            status = getattr(exc, "status_code", None)
            if status == 429 and "quota" in str(exc).lower():
                raise AzureOpenAiQuotaExceededError() from exc
            logger.exception("nexhire.openai.api_error", extra={"op": operation_name})
            raise AzureOpenAiError() from exc

    logger.error("nexhire.openai.retries_exhausted", extra={"op": operation_name})
    raise AzureOpenAiRateLimitedError() from last_exc


def _extract_tokens(response: Any) -> int | None:
    """Best-effort token extraction from an OpenAI SDK response.

    Different endpoints (chat/completions, embeddings) use different
    `.usage` shapes; fall back to None if anything is unfamiliar.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if isinstance(total, int):
        return total
    return None
