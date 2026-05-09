"""SQLAlchemy async engine, session factory, and DB helpers.

This module owns:
  * The single async engine for the whole app.
  * `Base` — declarative base for every ORM model.
  * `get_session` — FastAPI dependency that yields one session per request,
    auto-committing on clean return and rolling back on exceptions.
  * `execute_with_retry` — wraps a unit of work with exponential backoff
    against transient Postgres errors (Blueprint §17.7). Permanent errors
    (`IntegrityError`, etc.) bypass the retry and surface immediately so
    the error-handler middleware can map them to domain exceptions.

Notes:
  * `expire_on_commit=False` on the session — we frequently read attributes
    *after* commit (e.g. publishing events from the same session) and the
    default would otherwise force a re-fetch.
  * The engine uses a connection pool sized from settings; in production
    the values come from Key Vault references. For dev they default to 10/20.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from typing import Any, TypeVar

from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
)
from sqlalchemy.exc import (
    TimeoutError as SaTimeoutError,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from app.config import Settings, get_settings
from app.shared.exceptions import DatabaseUnavailableError

logger = logging.getLogger("nexhire.db")

T = TypeVar("T")


class Base(MappedAsDataclass, DeclarativeBase, kw_only=True):
    """SQLAlchemy declarative base.

    `MappedAsDataclass` gives every ORM model dataclass-style ergonomics
    (typed __init__, equality based on PK, slots-friendly) without the
    boilerplate. Models then look like:

        class User(Base):
            __tablename__ = "users"
            id: Mapped[UUID] = mapped_column(primary_key=True, ...)
            email: Mapped[str] = mapped_column(...)

    `kw_only=True` makes every generated `__init__` parameter keyword-only,
    which sidesteps the dataclass "non-default argument follows default"
    rule that bites when a model mixes `default_factory=uuid4` PKs with
    plain non-defaulted columns. All callers pass kwargs anyway.
    """


# ────────────────────────────────────────────────────────────────────
# Engine + session factory (module-level singletons).
# `_engine` is None until `init_engine` is called; tests call
# `init_engine(custom_settings)` to swap in a test DB.
# ────────────────────────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create the engine + session factory. Idempotent.

    Returns the engine for callers who want it directly (e.g. Alembic in
    online mode, or tests doing schema setup).
    """
    global _engine, _sessionmaker
    if _engine is not None:
        return _engine

    cfg = settings or get_settings()
    _engine = create_async_engine(
        cfg.database_url,
        pool_size=cfg.database_pool_size,
        max_overflow=cfg.database_pool_overflow,
        pool_pre_ping=True,    # detect stale conns from network drops
        pool_recycle=1_800,    # recycle after 30min (Azure idle timeout = 4min for some SKUs)
        echo=False,
        future=True,
    )
    _sessionmaker = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )
    logger.info("nexhire.db.engine_initialized")
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return init_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    """Tear down on app shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("nexhire.db.engine_disposed")


# ────────────────────────────────────────────────────────────────────
# Per-request session contextvar.
# Producers can stash deferred work (e.g. domain events to publish only
# after the request transaction commits) on `session.info`. The bus
# checks this contextvar via `current_request_session()` to decide
# whether to defer or publish immediately.
# ────────────────────────────────────────────────────────────────────
_current_request_session: ContextVar[AsyncSession | None] = ContextVar(
    "_current_request_session", default=None
)


def current_request_session() -> AsyncSession | None:
    """Return the session bound to the current FastAPI request, if any."""
    return _current_request_session.get()


# ────────────────────────────────────────────────────────────────────
# FastAPI dependency.
# ────────────────────────────────────────────────────────────────────
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one session per request.

    Pattern:
        async def endpoint(session: AsyncSession = Depends(get_session)):
            ...

    On clean return: commits. On exception: rolls back. Always closes.
    Drains any deferred-after-commit work (e.g. queued domain events)
    after a successful commit.
    """
    factory = get_sessionmaker()
    async with factory() as session:
        token = _current_request_session.set(session)
        try:
            yield session
            await session.commit()
            # Drain deferred work AFTER the producer's commit so handlers
            # that open their own session can see committed rows.
            await _run_after_commit_callbacks(session)
        except Exception:
            await session.rollback()
            raise
        finally:
            _current_request_session.reset(token)
            await session.close()


async def _run_after_commit_callbacks(session: AsyncSession) -> None:
    """Invoke any callables stashed on `session.info["after_commit"]`.

    Drains repeatedly: handlers can publish further events that the bus
    re-defers onto the same list (because the request context-var is
    still set during the drain). Loop until no new callbacks appear.

    Failures are logged but do not propagate — at this point the user's
    request has already succeeded; we don't want a flaky email handler
    to flip a 201 into a 500.
    """
    safety_limit = 32  # depth-cap to prevent infinite republishing.
    for _ in range(safety_limit):
        callbacks: list[Callable[[], Awaitable[None]]] = list(
            session.info.pop("after_commit", []) or []
        )
        if not callbacks:
            return
        for cb in callbacks:
            try:
                await cb()
            except Exception:
                logger.exception("nexhire.db.after_commit_failed")
    logger.warning(
        "nexhire.db.after_commit_drain_capped",
        extra={"safety_limit": safety_limit},
    )


# ────────────────────────────────────────────────────────────────────
# Retry helper (Blueprint §17.7).
# Distinguishes transient errors (retry with backoff) from permanent
# errors (re-raise immediately so error-handler can map them to domain
# exceptions like DUPLICATE_CANDIDATE_BLOCKED via constraint name).
# ────────────────────────────────────────────────────────────────────
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    OperationalError,    # connection drops, deadlocks
    SaTimeoutError,      # pool timeout
)
# IntegrityError and DataError MUST NOT retry — they're application bugs
# or expected constraint violations that must surface immediately.


async def execute_with_retry(
    operation: Callable[[AsyncSession], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay_seconds: float = 1.0,
) -> T:
    """Run `operation(session)` inside a transaction with exponential
    backoff against transient errors.

    Args:
        operation: async function taking a session and returning a value.
            The function MUST NOT call `session.commit()` itself — the
            wrapper handles transaction boundaries.
        max_retries: total attempts (including the first).
        base_delay_seconds: first-retry delay; doubles each attempt.

    Raises:
        The original exception if non-retryable.
        DatabaseUnavailableError if all retries exhausted.
    """
    factory = get_sessionmaker()
    last_exc: BaseException | None = None

    for attempt in range(max_retries):
        try:
            async with factory() as session, session.begin():
                return await operation(session)
        except IntegrityError:
            # Constraint violation — re-raise so error_handler can map.
            raise
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                logger.exception(
                    "nexhire.db.retry_exhausted",
                    extra={"attempts": max_retries},
                )
                raise DatabaseUnavailableError() from exc
            wait = base_delay_seconds * (2**attempt)
            logger.warning(
                "nexhire.db.transient_retry",
                extra={"attempt": attempt + 1, "wait_seconds": wait},
            )
            await asyncio.sleep(wait)
        except DBAPIError:
            raise

    # Defensive: should be unreachable, but keeps the type-checker happy.
    raise DatabaseUnavailableError() from last_exc


def map_integrity_error(exc: IntegrityError) -> Exception:
    """Map a Postgres constraint-violation to a domain exception.

    The middleware error handler invokes this when it sees an
    `IntegrityError`. Constraint *names* are the contract — keep them
    stable in migrations.

    Currently mapped:
      * `idx_referrals_active_pan` → DuplicateCandidateBlockedError
      * unique on `interns.non_worker_id` → NonWorkerIdAlreadyIssuedError

    Unknown constraint → return the original exception so it surfaces as
    a SystemError (`UNEXPECTED_ERROR`) and an alert fires. We never want
    silent fallback for unmapped IntegrityErrors.
    """
    from app.shared.exceptions import (
        DuplicateCandidateBlockedError,
        NonWorkerIdAlreadyIssuedError,
    )

    msg = str(getattr(exc, "orig", exc))
    if "idx_referrals_active_pan" in msg:
        return DuplicateCandidateBlockedError()
    if "non_worker_id" in msg and "unique" in msg.lower():
        return NonWorkerIdAlreadyIssuedError()
    return exc


# ────────────────────────────────────────────────────────────────────
# Health probe — used by /health (S0.7) once DB is required.
# ────────────────────────────────────────────────────────────────────
async def healthcheck() -> dict[str, Any]:
    from sqlalchemy import text

    factory = get_sessionmaker()
    try:
        async with factory() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.scalar_one()
            return {"status": "ok", "echo": row}
    except Exception as exc:
        logger.warning("nexhire.db.healthcheck_failed", exc_info=exc)
        return {"status": "down", "error": exc.__class__.__name__}
