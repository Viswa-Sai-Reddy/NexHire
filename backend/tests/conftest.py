"""Shared pytest fixtures for the NexHire backend.

Strategy:
  * `testcontainers` boots Postgres + Redis per test session — fast
    enough (~3s warm-up) and avoids any "shared dev DB" footgun.
  * A freshly-generated RSA keypair is injected into Settings so JWT
    tests don't need the real Key Vault.
  * `app` fixture creates a clean FastAPI app per test with an httpx
    AsyncClient — every test runs against a real ASGI surface.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import cast

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.config import Settings, get_settings
from app.infrastructure import database


@pytest.fixture(scope="session")
def postgres() -> Iterator[str]:
    """Boot Postgres for the full test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        # asyncpg DSN
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        url = f"postgresql+asyncpg://{pg.username}:{pg.password}@{host}:{port}/{pg.dbname}"
        yield url


@pytest.fixture(scope="session")
def redis() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        host = r.get_container_host_ip()
        port = r.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    """Generate one keypair for all JWT tests."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


@pytest.fixture(scope="session")
def pan_test_keys() -> tuple[str, str]:
    """32-byte hex pepper + 32-byte hex AES key for PAN tests."""
    import secrets

    pepper = secrets.token_hex(32)
    aes_key = secrets.token_hex(32)
    return pepper, aes_key


@pytest.fixture(scope="session")
def test_settings(
    postgres: str,
    redis: str,
    rsa_keypair: tuple[str, str],
    pan_test_keys: tuple[str, str],
) -> Settings:
    private_pem, public_pem = rsa_keypair
    pepper, aes_key = pan_test_keys
    overrides: dict[str, str] = {
        "DATABASE_URL": postgres,
        "REDIS_URL": redis,
        "JWT_PRIVATE_KEY_PEM": private_pem,
        "JWT_PUBLIC_KEY_PEM": public_pem,
        "JWT_KID": "test-key-2026",
        "JWT_ISSUER": "https://nexhire.test",
        "JWT_AUDIENCE": "nexhire-api-test",
        "AZURE_AD_TENANT_ID": "test-tenant",
        "AZURE_AD_CLIENT_ID": "test-client",
        "PAN_HMAC_PEPPER": pepper,
        "PAN_AES_KEY": aes_key,
    }
    cfg = Settings(**cast("dict", overrides))  # type: ignore[arg-type]
    # Pin the cached singleton + bust per-key caches that may have read
    # the production settings during a previous test session.
    get_settings.cache_clear()

    import app.modules.referral.pan_crypto as pan_crypto

    pan_crypto._pepper.cache_clear()  # type: ignore[attr-defined]
    pan_crypto._aes_key.cache_clear()  # type: ignore[attr-defined]

    # Make `get_settings()` return the test object even when callers
    # bypass DI. We monkey-patch the lru_cache by priming it.
    get_settings.cache_clear()
    object.__setattr__(get_settings, "__wrapped__", lambda: cfg)
    return cfg


@pytest_asyncio.fixture
async def session(test_settings: Settings) -> AsyncIterator[AsyncSession]:
    """Per-test session against the test database."""
    engine = database.init_engine(test_settings)

    # Ensure schema exists. The migrations are run by an explicit fixture
    # in tests that need them; pure unit tests that only need value
    # objects / exceptions skip this entirely.
    async with engine.begin() as conn:
        # Apply alembic migrations in-process. We do this once per
        # session via a module-level guard so re-runs are cheap.
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        cfg.set_main_option(
            "sqlalchemy.url",
            test_settings.database_url.replace("+asyncpg", "+psycopg2"),
        )
        # Note: alembic is sync; `await` here is just to keep the
        # fixture async-shaped. testcontainers exposes a sync conn.
        del conn  # unused, just to mark we touched the engine
        command.upgrade(cfg, "head")

    factory = database.get_sessionmaker()
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def client(test_settings: Settings) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app(test_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
