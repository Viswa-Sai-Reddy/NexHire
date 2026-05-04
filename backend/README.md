# NexHire Backend

Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic · Modular Monolith.

## Layout

```
app/
├─ main.py              # FastAPI app entry
├─ config.py            # pydantic-settings; reads .env + Key Vault
├─ shared/              # value objects, exceptions, domain events, constants
├─ infrastructure/      # database, event_bus, scheduler, Azure clients
├─ middleware/          # audit, auth, error_handler, logging, rate_limit
└─ modules/             # feature modules: auth, referral, mentor, ai, ...
   └─ <module>/
      ├─ router.py      # FastAPI router
      ├─ service.py     # business logic
      ├─ repository.py  # SQLAlchemy queries
      ├─ models.py      # ORM models
      ├─ schemas.py     # Pydantic request/response
      └─ event_handlers.py  # domain event reactions
migrations/             # Alembic; one file per migration
tests/                  # unit + integration (testcontainers)
```

## Commands

```bash
uv sync                          # install deps
uv run fastapi dev app/main.py   # dev server with reload
uv run alembic upgrade head      # apply all migrations
uv run alembic revision --autogenerate -m "describe change"
uv run pytest                    # run tests
uv run ruff check .              # lint
uv run ruff format .             # format
uv run mypy app                  # type-check
```

## Configuration

All runtime config lives in `app/config.py` (pydantic-settings). Local dev: `.env` file. Production: Azure Key Vault references resolved by `azure-identity` `DefaultAzureCredential`.

See `.env.example` for the full variable list.
