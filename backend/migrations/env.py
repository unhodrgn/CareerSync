"""Alembic environment: DB URL from app settings, metadata from app models."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.core.config import settings
from app.db.session import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

# Q42, D70: PostgreSQL stores `lower(trim(name))` as `lower(TRIM(BOTH FROM name))` and Alembic compares the expression text, so
# `alembic check` reports this index as removed and added again although nothing differs. The model keeps `lower(trim(name))`
# because SQLite cannot parse `TRIM(BOTH FROM ...)`. Narrow on purpose: this one index name.
# shortcut: a real change to this index is also hidden from autogenerate, so review a change to it by hand.
IGNORED_INDEXES = frozenset({"uq_job_criteria_job_name"})


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "index" and name in IGNORED_INDEXES)


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
