"""Azure OpenAI async client wrapper.

S1 fills this in fully (resume parser, mentor matcher, risk profiler,
chatbot, certificate generator). S0 ships a minimal singleton + retry
shape so the AI-service module can import without surprises.

Behaviour locked:
  * Exponential backoff on rate limits (1s, 2s, 4s, 8s) — Blueprint §17.6.
  * Quota-exceeded → AzureOpenAiQuotaExceededError → flows degrade.
  * Cost tracking via App Insights custom metric (B23) — TODO in S1.
"""
from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

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


@lru_cache(maxsize=1)
def get_client() -> "AsyncAzureOpenAI":
    from openai import AsyncAzureOpenAI

    cfg = get_settings()
    if not cfg.azure_openai_endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is not configured")
    return AsyncAzureOpenAI(
        api_key=cfg.azure_openai_api_key,
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.azure_openai_endpoint,
    )


async def call_with_retry[T](operation_name: str, fn, *args, **kwargs) -> T:  # type: ignore[no-untyped-def]
    """Run an OpenAI SDK call with exponential backoff against
    `RateLimitError`. Quota errors re-raise immediately (no retry helps).

    `fn` is the bound coroutine-returning method (e.g.
    `client.chat.completions.create`). Kept untyped — the SDK has many
    differing call signatures and we don't want to over-fit the wrapper.
    """
    from openai import APIError, APITimeoutError, RateLimitError

    last_exc: BaseException | None = None
    for delay in _RETRY_DELAYS_SECONDS:
        try:
            return await fn(*args, **kwargs)
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
            # 429 quota / 5xx → don't burn the retry budget
            status = getattr(exc, "status_code", None)
            if status == 429 and "quota" in str(exc).lower():
                raise AzureOpenAiQuotaExceededError() from exc
            logger.exception("nexhire.openai.api_error", extra={"op": operation_name})
            raise AzureOpenAiError() from exc

    logger.error("nexhire.openai.retries_exhausted", extra={"op": operation_name})
    raise AzureOpenAiRateLimitedError() from last_exc
