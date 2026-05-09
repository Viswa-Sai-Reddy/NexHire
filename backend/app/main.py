"""NexHire FastAPI application entry.

Wires:
  * Settings + structured logging.
  * Database engine lifecycle.
  * Redis client lifecycle.
  * APScheduler boot/shutdown.
  * Event bus singleton (handlers self-register at module import).
  * Global error handlers.
  * Routers: auth, jwks, /health.

Slices S1+ append their routers here as the app grows.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.infrastructure import azure_keyvault, redis_client
from app.infrastructure.database import (
    dispose_engine,
    init_engine,
)
from app.infrastructure.database import (
    healthcheck as db_health,
)
from app.infrastructure.event_bus import get_bus
from app.infrastructure.redis_client import healthcheck as redis_health
from app.infrastructure.scheduler import (
    init_scheduler,
    shutdown_scheduler,
    start_scheduler,
)
from app.middleware.error_handler import register_error_handlers
from app.middleware.logging import RequestIdMiddleware, configure_logging
from app.modules.access.router import access_router
from app.modules.admin.router import admin_router
from app.modules.auth.router import auth_router, jwks_router
from app.modules.lifecycle.router import lifecycle_router
from app.modules.mentor.picker_router import picker_router as mentor_picker_router
from app.modules.mentor.router import router as mentor_action_router
from app.modules.nda.webhook_router import webhook_router as opensign_webhook_router
from app.modules.onboarding.router import candidate_router, hr_onboarding_router
from app.modules.referral.college_router import college_router
from app.modules.referral.hr_router import hr_router
from app.modules.referral.router import referral_router

logger = logging.getLogger("nexhire")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    configure_logging()
    logger.info("nexhire.startup", extra={"env": cfg.nexhire_env})

    # Engines + clients are lazy elsewhere, but init the DB here so a
    # mis-configured DSN fails fast on boot, not on first request.
    init_engine(cfg)
    init_scheduler()
    # Wire every module's event subscriptions before the scheduler
    # starts, so any background job that publishes can be handled.
    from app.wiring import register_all

    register_all(get_bus())

    # Register scheduled background jobs before the scheduler starts.
    from app.infrastructure import outbox_worker
    from app.modules.ai import bottleneck_job, compliance_job
    from app.modules.mentor import timeout_job as mentor_timeout_job
    from app.modules.nda import timeout_job as nda_timeout_job
    from app.modules.referral import cooling_reminder_job
    from app.modules.workflow import sla_breach_job

    mentor_timeout_job.register()
    nda_timeout_job.register()
    compliance_job.register()
    cooling_reminder_job.register()
    bottleneck_job.register()
    sla_breach_job.register()
    outbox_worker.register()
    await start_scheduler()

    try:
        yield
    finally:
        logger.info("nexhire.shutdown")
        await shutdown_scheduler()
        await redis_client.close()
        await azure_keyvault.close()
        await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    app = FastAPI(
        title="NexHire API",
        version="0.1.0",
        description="AI-powered intern referral management — modular monolith.",
        lifespan=lifespan,
        docs_url="/docs" if not cfg.is_production else None,
        redoc_url="/redoc" if not cfg.is_production else None,
    )

    # Order matters: outermost first.
    # CORS handles browser preflight OPTIONS calls from the SPA.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cfg.frontend_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)

    # JWKS is unprefixed (RFC 8414).
    app.include_router(jwks_router)

    api_prefix = cfg.nexhire_api_prefix.rstrip("/")
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(referral_router, prefix=api_prefix)
    app.include_router(hr_router, prefix=api_prefix)
    app.include_router(candidate_router, prefix=api_prefix)
    app.include_router(hr_onboarding_router, prefix=api_prefix)
    app.include_router(access_router, prefix=api_prefix)
    app.include_router(lifecycle_router, prefix=api_prefix)
    app.include_router(admin_router, prefix=api_prefix)
    app.include_router(opensign_webhook_router, prefix=api_prefix)
    app.include_router(college_router, prefix=api_prefix)
    app.include_router(mentor_picker_router, prefix=api_prefix)
    # Mentor action tokens are intentionally unprefixed so the URLs in
    # email links stay short and stable regardless of API versioning.
    app.include_router(mentor_action_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, object]:
        """Liveness + readiness. Probes DB + Redis but degrades gracefully
        in dev when those aren't running."""
        return {
            "status": "ok",
            "env": cfg.nexhire_env,
            "db": await db_health(),
            "redis": await redis_health(),
        }

    return app


app = create_app()
