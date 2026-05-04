# NexHire

AI-powered intern referral management platform — modular monolith built on FastAPI + React.

See [`docs/Implementation_Plan.md`](docs/Implementation_Plan.md) for the binding decision log and build sequence. Spec sources are [`docs/System_Blueprint.md`](docs/System_Blueprint.md) and [`docs/System_Flow.md`](docs/System_Flow.md).

## Quick start

### Backend (Python 3.12 + FastAPI, uv-managed)

```bash
cd backend
cp .env.example .env        # fill in real values
uv sync                     # install deps + create .venv
uv run alembic upgrade head # apply migrations
uv run fastapi dev app/main.py
# → http://localhost:8000/health
```

### Frontend (React 18 + TS + Vite, pnpm-managed)

```bash
cd frontend
cp .env.example .env.local  # fill in real values
pnpm install
pnpm dev
# → http://localhost:5173
```

## Repo layout

- [`backend/`](backend/) — Python FastAPI modular monolith.
- [`frontend/`](frontend/) — React SPA.
- [`docs/`](docs/) — spec, plan, ADRs.
- [`.github/workflows/`](.github/workflows/) — CI.

## Conventions

| Topic | Choice |
|---|---|
| Backend pkg manager | `uv` |
| Frontend pkg manager | `pnpm` |
| Lint/format | `ruff` (Python) · `eslint`+`prettier` (TS) |
| Type-check | `mypy --strict` (Python) · `tsc --strict` (TS) |
| API prefix | `/api/v1/...` |
| Commit style | Conventional Commits |
| Branch model | Trunk-based; short-lived feature branches |
| Time storage | UTC TIMESTAMPTZ; display IST |
