# Backend

## Database migrations (Alembic)

Prerequisites: Docker DB running (`docker compose up -d` from repo root) and a filled-in
repo-root `.env` (copy `.env.example`).

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\alembic upgrade head      # create / update all tables
.venv\Scripts\alembic current           # show applied revision (0001)
.venv\Scripts\alembic downgrade base    # DROP everything (destroys data)
```

`DATABASE_URL` may use `postgresql+asyncpg://...` for the app; migrations swap in the
sync `psycopg` driver automatically. If `DATABASE_URL` is not set, it is built from
`POSTGRES_USER/PASSWORD/DB` on `127.0.0.1:5433`.

New migration: `.venv\Scripts\alembic revision -m "describe change"`, then write the SQL
in `upgrade()` / `downgrade()`. Never edit 0001 after teammates have applied it.

## Schema tests

Needs the DB up and migrated to head. Every test runs in a transaction that is rolled
back, so no data is left in the dev database.

```powershell
cd backend
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```
