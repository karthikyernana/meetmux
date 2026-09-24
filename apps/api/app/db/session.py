"""SQLAlchemy async engine and session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    pass


# Ensure all domain models are imported for SQLAlchemy mapper resolution
import app.domains.workspaces.models  # noqa: F401, E402
import app.domains.workload.models  # noqa: F401, E402
import app.domains.plans.models  # noqa: F401, E402
import app.domains.indexes.models  # noqa: F401, E402
import app.domains.experiments.models  # noqa: F401, E402


def _build_async_engine() -> object:
    settings = get_settings()
    dsn = str(settings.database_url)
    return create_async_engine(
        dsn,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def _build_sync_engine() -> object:
    settings = get_settings()
    # Convert async DSN (postgresql+psycopg) → sync (postgresql+psycopg)
    dsn = str(settings.database_url).replace("+asyncpg", "").replace("+aiosqlite", "")
    # Keep psycopg driver but use sync URL scheme
    dsn = dsn.replace("postgresql+psycopg://", "postgresql+psycopg://")
    return create_engine(dsn, echo=settings.debug, pool_pre_ping=True)


engine = _build_async_engine()
sync_engine = _build_sync_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Context manager that yields a synchronous DB session (for RQ workers)."""
    session = SyncSessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
