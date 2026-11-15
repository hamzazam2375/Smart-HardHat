"""Alembic environment. DB URL comes from app/db_url.py (repo-root .env)."""
from alembic import context
from sqlalchemy import create_engine, pool

from app.db_url import database_url

config = context.config
target_metadata = None  # migrations are hand-written SQL, no autogenerate


def run_migrations_offline() -> None:
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
