# Local Setup Guide

How to run NexHire end-to-end on a fresh machine. NexHire is a modular monolith with two apps that must run together: a Python FastAPI backend and a React/Vite frontend. The backend depends on PostgreSQL, Redis, and several Azure services.

## 1. System-level dependencies

Install once per laptop.

| Tool | Version | Purpose | Install (Windows) |
|---|---|---|---|
| Python | 3.12 (`>=3.12,<3.13`) | Backend runtime | `winget install Python.Python.3.12` |
| `uv` | latest | Python package manager | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Node.js | >= 20 LTS | Frontend runtime | `winget install OpenJS.NodeJS.LTS` |
| `pnpm` | 9.x | Frontend package manager | `npm install -g pnpm@9` (or `corepack enable`) |
| Git | any recent | Clone repo | `winget install Git.Git` |
| PostgreSQL | 15+ | Backend database | https://www.postgresql.org/download/windows/ — or Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:15` |
| Redis | 6+ | Cache / sessions | WSL2 + `apt install redis`, or Docker: `docker run -d -p 6379:6379 redis:7` |

Verify:

```powershell
python --version    # 3.12.x
uv --version
node --version      # v20+
pnpm --version      # 9.x
psql --version
```

## 2. Get the code

```powershell
git clone <repo-url> NexHire
cd NexHire
```

If copying files manually instead of cloning, exclude `node_modules/`, `.venv/`, `dist/`, and the `.env*` files — those are machine-specific.

## 3. Backend setup (`backend/`)

```powershell
cd backend
copy .env.example .env       # then edit .env (see "Required env vars" below)
uv sync                      # creates .venv, installs all Python deps from pyproject.toml + uv.lock
uv run alembic upgrade head  # applies all DB migrations to the database in DATABASE_URL
uv run fastapi dev app/main.py
# → http://localhost:8000/health  should return 200 OK
# → http://localhost:8000/docs    Swagger UI
```

### Required env vars in `backend/.env`

**Will not start without these:**

- `DATABASE_URL` — e.g. `postgresql+asyncpg://postgres:dev@localhost:5432/nexhire`
- `REDIS_URL` — e.g. `redis://localhost:6379/0`
- `JWT_PRIVATE_KEY_PEM`, `JWT_PUBLIC_KEY_PEM`, `JWT_KID`, `JWT_ISSUER`, `JWT_AUDIENCE` — defaults provided in `.env.example` are usable for local dev

**Required for Azure AD login (any auth-protected endpoint):**

- `AZURE_AD_TENANT_ID`, `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET`
- `AZURE_AD_REDIRECT_URI=http://localhost:5173/auth/callback`

**Required only if you exercise the corresponding feature:**

| Feature | Env vars |
|---|---|
| AI features | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_*` |
| Resume parsing | `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY` |
| File uploads | `AZURE_BLOB_ACCOUNT_URL`, container names |
| Email | `GMAIL_SERVICE_ACCOUNT_JSON_PATH`, `GMAIL_SENDER_EMAIL` |
| AD provisioning | `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` |
| Document signing | `OPENSIGN_BASE_URL`, `OPENSIGN_API_KEY` |
| PAN encryption | `PAN_HMAC_PEPPER` (32+ random hex bytes), `PAN_AES_KEY` (32-byte base64 AES-256 key) |

**Bootstrap first superuser (optional but recommended):**

- `SEED_PROGRAM_OWNER_EMAIL`, `SEED_PROGRAM_OWNER_NAME`

### Create the database before running migrations

```powershell
psql -U postgres -c "CREATE DATABASE nexhire;"
```

Then `uv run alembic upgrade head` will create all tables.

### Useful backend commands

```powershell
uv run pytest                                       # tests
uv run ruff check .                                 # lint
uv run ruff format .                                # format
uv run mypy app                                     # strict type-check
uv run alembic revision --autogenerate -m "msg"    # new migration
```

## 4. Frontend setup (`frontend/`)

```powershell
cd ..\frontend
copy .env.example .env.local   # edit .env.local
pnpm install                   # installs deps from pnpm-lock.yaml
pnpm dev
# → http://localhost:5173
```

### Required env vars in `frontend/.env.local`

- `VITE_API_BASE_URL=http://localhost:8000/api/v1`
- `VITE_AZURE_AD_CLIENT_ID`, `VITE_AZURE_AD_TENANT_ID`, `VITE_AZURE_AD_REDIRECT_URI` — must match the backend's Azure AD app registration
- `VITE_APP_INSIGHTS_CONNECTION_STRING` — optional

### Useful frontend commands

```powershell
pnpm dev          # dev server (hot reload) on :5173
pnpm build        # production build to dist/
pnpm preview      # serve the production build
pnpm typecheck    # tsc --strict, no emit
pnpm lint
pnpm test         # vitest
```

## 5. Daily startup (after one-time setup)

Open two terminals.

**Terminal 1 — backend:**

```powershell
cd NexHire\backend
uv run fastapi dev app/main.py
```

**Terminal 2 — frontend:**

```powershell
cd NexHire\frontend
pnpm dev
```

Open http://localhost:5173. The frontend proxies `/api/v1/*` to the backend on :8000.

## 6. Verification checklist

- [ ] `python --version` shows 3.12.x; `node --version` shows v20+
- [ ] `psql -U postgres -l` lists the `nexhire` database
- [ ] `redis-cli ping` → `PONG` (or container is running)
- [ ] `cd backend && uv run alembic current` shows the latest migration revision
- [ ] http://localhost:8000/health returns 200
- [ ] http://localhost:8000/docs shows the FastAPI Swagger UI
- [ ] http://localhost:5173 loads the React app and the login button triggers Azure AD redirect
- [ ] Logging in as the `SEED_PROGRAM_OWNER_EMAIL` user lands on the dashboard

## 7. Things that won't transfer with the code

These have to be re-obtained or recreated on the new laptop:

- **Azure AD app registration secrets** (`AZURE_AD_CLIENT_SECRET`) — rotate or copy from your password manager
- **Azure OpenAI / Document Intelligence keys** — same
- **Gmail service account JSON file** (`GMAIL_SERVICE_ACCOUNT_JSON_PATH`) — copy the JSON file separately, do not commit
- **`PAN_AES_KEY` and `PAN_HMAC_PEPPER`** — for local dev you can generate fresh ones, but if you're connecting to a database with already-encrypted PAN data you MUST reuse the originals or the data won't decrypt
- **The PostgreSQL database itself** — either dump/restore from the old laptop (`pg_dump` / `pg_restore`) or start fresh with `alembic upgrade head` + reseed
