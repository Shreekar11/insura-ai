"""Neo4j client configuration and connection management."""

from typing import Optional
from neo4j import AsyncDriver, AsyncSession, AsyncGraphDatabase
from app.core.config import settings
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class Neo4jClientManager:
    """Manages Neo4j driver and sessions."""

    _driver: Optional[AsyncDriver] = None

    @classmethod
    async def get_driver(cls) -> AsyncDriver:
        """Get or create Neo4j driver."""
        if cls._driver is None:
            # Use neo4j:// protocol for local development
            uri = f"neo4j://{settings.neo4j.host}:{settings.neo4j.port}"
            cls._driver = AsyncGraphDatabase.driver(
                uri,
                auth=(settings.neo4j.username, settings.neo4j.password),
            )
            LOGGER.info("Neo4j driver initialized", extra={"uri": uri})
        return cls._driver

    @classmethod
    async def close(cls) -> None:
        """Close Neo4j driver."""
        if cls._driver:
            await cls._driver.close()
            cls._driver = None
            LOGGER.info("Neo4j driver closed")

    @classmethod
    async def get_session(cls, database: Optional[str] = None) -> AsyncSession:
        """Get Neo4j async session."""
        driver = await cls.get_driver()
        return driver.session(database=database or settings.neo4j.database)


async def get_neo4j_driver() -> AsyncDriver:
    """Dependency for getting Neo4j driver."""
    return await Neo4jClientManager.get_driver()

async def init_neo4j() -> None:
    """Initialize Neo4j connection."""
    await Neo4jClientManager.get_driver()

async def close_neo4j() -> None:
    """Close Neo4j connection."""
    await Neo4jClientManager.close()
