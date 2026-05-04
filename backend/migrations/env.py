"""Alembic env wiring.

Reads the database URL from `app.config.Settings` so we never duplicate it.
Targets a placeholder `MetaData` object until S0.3 introduces the SQLAlchemy
declarative base; until then `--autogenerate` will see an empty model and
emit empty migrations (intentional).
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from app.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# asyncpg URL is for runtime; alembic uses the sync driver.
sync_url = settings.database_url.replace("+asyncpg", "+psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)


# Import every module that defines ORM models so Base.metadata is fully
# populated. Adding a new model? Add an import line here.
from app.infrastructure.database import Base  # noqa: E402
from app.infrastructure import outbox_models  # noqa: E402, F401
from app.modules.auth import models as _auth_models  # noqa: E402, F401
from app.modules.referral import models as _referral_models  # noqa: E402, F401
from app.modules.onboarding import models as _onboarding_models  # noqa: E402, F401
from app.modules.nda import models as _nda_models  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`--sql` mode: emits SQL without connecting."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Live-DB mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
