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

## Mock data (dev only)

Seeds every table with small, linked, clearly mock data (`MOCK-*` codes,
`@mock.smarthardhat.test` accounts, `mock:` event keys, `[MOCK]` notes). It does not
change the schema. Scenarios and flag-bit conventions are listed in the script docstring.

```powershell
cd backend
.venv\Scripts\python -m scripts.seed_mock_data           # seed; rerunning adds nothing
.venv\Scripts\python -m scripts.seed_mock_data --reset   # wipe mock rows, reseed relative to now
.venv\Scripts\python -m scripts.seed_mock_data --delete  # wipe mock rows only
```

Timestamps are relative to the first seed time, so "live" devices go stale after 3 min.
Run `--reset` just before a demo. Mock accounts cannot sign in unless `MOCK_ACCOUNT_PASSWORD`
is set (requires `argon2-cffi`) on a fresh seed. Refuses non-local hosts without
`--allow-remote`.
