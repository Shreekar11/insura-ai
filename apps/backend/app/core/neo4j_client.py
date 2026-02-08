"""Neo4j client configuration and connection management."""

import asyncio
from typing import Any, Optional
from neo4j import AsyncDriver, AsyncSession, AsyncGraphDatabase
from neo4j.exceptions import (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)
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

    # All entity node labels that can appear in the graph
    ENTITY_LABELS = [
        "Policy", "Coverage", "Organization", "Claim",
        "Endorsement", "Location", "Condition", "Definition",
        "Exclusion", "Vehicle", "Driver", "VectorEmbedding",
        "Evidence",  # Added in Phase 5
    ]

    @classmethod
    async def ensure_constraints(cls) -> None:
        """Ensure uniqueness constraints exist for entity IDs."""
        driver = await cls.get_driver()

        async with driver.session(database=settings.neo4j.database) as session:
            # Entity node constraints: unique on `id`
            for label in cls.ENTITY_LABELS:
                constraint_name = f"constraint_{label.lower()}_id_unique"
                cypher = f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                try:
                    await session.run(cypher)
                    LOGGER.info(f"Ensured constraint for {label}", extra={"constraint": constraint_name})
                except Exception as e:
                    LOGGER.error(f"Failed to create constraint for {label}: {e}")

            # VectorEmbedding: unique on (entity_id, workflow_id)
            try:
                await session.run(
                    "CREATE CONSTRAINT constraint_vectorembedding_entityid_workflow_unique "
                    "IF NOT EXISTS FOR (n:VectorEmbedding) "
                    "REQUIRE (n.entity_id, n.workflow_id) IS UNIQUE"
                )
                LOGGER.info("Ensured composite constraint for VectorEmbedding")
            except Exception as e:
                LOGGER.error(f"Failed to create VectorEmbedding constraint: {e}")

    @classmethod
    async def ensure_indexes(cls) -> None:
        """Ensure composite and standalone indexes for efficient MATCH queries."""
        driver = await cls.get_driver()

        async with driver.session(database=settings.neo4j.database) as session:
            for label in cls.ENTITY_LABELS:
                # Composite index on (id, workflow_id) for MERGE patterns
                composite_name = f"idx_{label.lower()}_id_workflow"
                try:
                    await session.run(
                        f"CREATE INDEX {composite_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.id, n.workflow_id)"
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to create composite index for {label}: {e}")

                # Standalone workflow_id index for workflow-scoped queries
                wf_name = f"idx_{label.lower()}_workflow"
                try:
                    await session.run(
                        f"CREATE INDEX {wf_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.workflow_id)"
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to create workflow index for {label}: {e}")

            LOGGER.info("Ensured indexes for all entity labels")

    @classmethod
    async def run_query(
        cls,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> list[dict[str, Any]]:
        """
        Execute a Cypher query with retry logic for transient failures.

        Args:
            query: Cypher query string
            parameters: Query parameters dictionary
            database: Database name (defaults to configured database)
            max_retries: Maximum retry attempts for transient errors
            retry_delay: Initial delay between retries in seconds (exponential backoff)

        Returns:
            List of result records as dictionaries

        Raises:
            ServiceUnavailable: Neo4j service is unavailable after retries
            Exception: Non-transient errors
        """
        parameters = parameters or {}
        db = database or settings.neo4j.database

        for attempt in range(max_retries):
            try:
                async with cls.get_session(database=db) as session:
                    result = await session.run(query, parameters)
                    records = await result.data()
                    return records

            except (ServiceUnavailable, SessionExpired, TransientError) as e:
                if attempt == max_retries - 1:
                    LOGGER.error(
                        f"Neo4j query failed after {max_retries} attempts",
                        extra={
                            "query": query[:100],
                            "error": str(e),
                            "attempts": max_retries,
                        },
                    )
                    raise

                # Exponential backoff
                wait_time = retry_delay * (2**attempt)
                LOGGER.warning(
                    f"Neo4j transient error, retrying in {wait_time}s",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(e),
                    },
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                LOGGER.error(
                    "Neo4j query failed with non-transient error",
                    extra={
                        "query": query[:100],
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

        return []

    @classmethod
    async def execute_write_query(
        cls,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a write query (CREATE, MERGE, SET, DELETE) in a transaction.

        Args:
            query: Cypher write query
            parameters: Query parameters
            database: Database name

        Returns:
            Query execution summary
        """
        parameters = parameters or {}
        db = database or settings.neo4j.database

        async with cls.get_session(database=db) as session:
            result = await session.run(query, parameters)
            summary = await result.consume()

            return {
                "nodes_created": summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set": summary.counters.properties_set,
                "nodes_deleted": summary.counters.nodes_deleted,
                "relationships_deleted": summary.counters.relationships_deleted,
            }


async def get_neo4j_driver() -> AsyncDriver:
    """Dependency for getting Neo4j driver."""
    return await Neo4jClientManager.get_driver()

async def init_neo4j(ensure_constraints: bool = True) -> None:
    """Initialize Neo4j connection and ensure constraints and indexes."""
    await Neo4jClientManager.get_driver()
    if ensure_constraints:
        await Neo4jClientManager.ensure_constraints()
        await Neo4jClientManager.ensure_indexes()

async def close_neo4j() -> None:
    """Close Neo4j connection."""
    await Neo4jClientManager.close()
