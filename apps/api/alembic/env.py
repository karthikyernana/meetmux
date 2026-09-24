"""
Alembic migration environment.
Imports all domain models so autogenerate can detect schema changes.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Import Base + all models (so Alembic can see tables) ─────────────────────
from app.db.session import Base  # noqa: F401

# Import all models to register them with Base.metadata
from app.domains.workspaces.models import Workspace, Connection  # noqa: F401
from app.domains.workload.models import WorkloadSnapshot, QueryFingerprint, QueryObservation  # noqa: F401
from app.domains.plans.models import PlanSnapshot  # noqa: F401
from app.domains.indexes.models import IndexCandidate, IndexRecord  # noqa: F401
from app.domains.experiments.models import Experiment, Recommendation, MigrationArtifact  # noqa: F401

config = context.config

# Override sqlalchemy.url from environment if present
database_url = os.getenv("DATABASE_URL", "")
if database_url:
    # Alembic needs sync URL — strip async driver prefix
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
