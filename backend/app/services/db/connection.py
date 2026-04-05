"""Async database connection pool using SQLAlchemy + asyncpg.

Provides a managed async session factory for PostgreSQL. The pool is
initialized during app startup via ``lifespan`` and torn down on
shutdown.

Usage:
    from app.services.db import db

    # In an endpoint / service function:
    async with db.session() as session:
        result = await session.execute(select(Session))
        rows = result.scalars().all()

    # Health check:
    healthy = await db.health_check()
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.logger import get_logger

logger = get_logger(__name__)


class Database:
    """Async database connection pool wrapper."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def is_connected(self) -> bool:
        return self._engine is not None

    async def connect(
        self,
        database_url: str,
        *,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        echo: bool = False,
    ) -> None:
        """Create the async engine and session factory.

        Call once during application startup. The ``database_url`` must
        use the ``postgresql+asyncpg://`` scheme.
        """
        if self._engine is not None:
            logger.warning("Database already connected - skipping")
            return

        # Ensure asyncpg driver
        url = database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not url.startswith("postgresql+asyncpg://"):
            url = f"postgresql+asyncpg://{url}"

        self._engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
            echo=echo,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info(f"Database pool created (size={pool_size}, overflow={max_overflow})")

    async def disconnect(self) -> None:
        """Dispose of the engine and connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database pool disposed")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a transactional async session.

        Commits on clean exit, rolls back on exception.
        """
        if self._session_factory is None:
            raise RuntimeError("Database not connected. Call db.connect() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        """Run a lightweight query to verify the connection is alive."""
        if self._engine is None:
            return False

        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            return False


# * Global instance
db = Database()
