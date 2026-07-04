"""
Alembic environment - sync engine (psycopg2) against the app's resolved database URL
"""

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import config as app_config
from app.model.orm import Base

config = context.config
target_metadata = Base.metadata

# ? CLI runs may not carry a URL; fall back to the app config (env/.env driven)
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", app_config.resolved_database_url)


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
