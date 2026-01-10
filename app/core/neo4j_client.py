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

    @classmethod
    async def ensure_constraints(cls) -> None:
        """Ensure uniqueness constraints exist for entity IDs."""
        driver = await cls.get_driver()
        labels = [
            "Policy", "Coverage", "Organization", "Claim", 
            "Endorsement", "Location", "Condition", "Definition"
        ]
        
        async with driver.session(database=settings.neo4j.database) as session:
            for label in labels:
                constraint_name = f"constraint_{label.lower()}_id_unique"
                cypher = f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                try:
                    await session.run(cypher)
                    LOGGER.info(f"Ensured constraint for {label}", extra={"constraint": constraint_name})
                except Exception as e:
                    LOGGER.error(f"Failed to create constraint for {label}: {e}")


async def get_neo4j_driver() -> AsyncDriver:
    """Dependency for getting Neo4j driver."""
    return await Neo4jClientManager.get_driver()

async def init_neo4j() -> None:
    """Initialize Neo4j connection and ensure constraints."""
    await Neo4jClientManager.get_driver()
    await Neo4jClientManager.ensure_constraints()

async def close_neo4j() -> None:
    """Close Neo4j connection."""
    await Neo4jClientManager.close()
