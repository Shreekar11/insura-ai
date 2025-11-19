"""Database session dependency for FastAPI."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import async_session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting async database session.

    Yields:
        AsyncSession: Database session
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

