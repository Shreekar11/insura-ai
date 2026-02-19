"""Database session dependency for FastAPI.

This module centralizes the async SQLAlchemy session dependency in the
core layer so it can be reused across the application.
"""

from collections.abc import AsyncGenerator
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, async_sessionmaker, create_async_engine
from app.core.config import settings
from sqlalchemy import text

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass

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


# Create async engine
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.database_echo,
    future=True,
    # Disable prepared statement cache for PgBouncer compatibility
    connect_args={"statement_cache_size": 0},
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db_session() -> AsyncSession:
    """Get async database session.

    Yields:
        AsyncSession: Database session
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


class DatabaseClient:
    """PostgreSQL database client with connection and migration management."""

    def __init__(self, engine: AsyncEngine):
        """Initialize database client.
        
        Args:
            engine: SQLAlchemy async engine
        """
        self.engine = engine
        self._connected = False

    async def connect(self) -> bool:
        """Test database connection."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.commit()
            
            self._connected = True
            LOGGER.info("Database connection successful")
            return True
            
        except Exception as e:
            self._connected = False
            LOGGER.error("Database connection failed", exc_info=True)
            raise

    async def disconnect(self) -> None:
        """Close database connection."""
        try:
            await self.engine.dispose()
            self._connected = False
            LOGGER.info("Database connection closed")
        except Exception as e:
            LOGGER.error(
                "Error closing database connection",
                exc_info=True,
                extra={"error": str(e)}
            )

    async def create_tables(self) -> None:
        """Create all database tables from SQLAlchemy models.
        
        This will create tables that don't exist without dropping existing ones.
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            LOGGER.info("Database tables created/verified successfully")
            
        except Exception as e:
            LOGGER.error(
                "Failed to create database tables",
                exc_info=True,
                extra={"error": str(e)}
            )
            raise

    async def drop_tables(self) -> None:
        """Drop all database tables.
        
        WARNING: This will delete all data!
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            
            LOGGER.warning("All database tables dropped")
            
        except Exception as e:
            LOGGER.error(
                "Failed to drop database tables",
                exc_info=True,
                extra={"error": str(e)}
            )
            raise

    async def auto_migrate(self, drop_existing: bool = False) -> None:
        """Auto-migrate database schema.
        
        Args:
            drop_existing: If True, drop existing tables before creating (WARNING: data loss!)
        """
        try:
            LOGGER.info("Starting auto-migration", extra={"drop_existing": drop_existing})
            
            if drop_existing:
                LOGGER.warning("Dropping existing tables...")
                await self.drop_tables()
            
            LOGGER.info("Creating/updating tables...")
            await self.create_tables()
            
            LOGGER.info("Auto-migration completed successfully")
            
        except Exception as e:
            LOGGER.error(
                "Auto-migration failed",
                exc_info=True,
                extra={"error": str(e)}
            )
            raise

    async def health_check(self) -> dict:
        """Check database health."""
        try:
            # We use a context manager to ensure the connection is closed
            async with self.engine.connect() as conn:
                # Use scalar() to retrieve the '1' and confirm data flow
                val = await conn.scalar(text("SELECT 1"))
                
            # If we reached here, the DB is responsive
            self._connected = True 
            
            return {
                "status": "healthy",
                "connected": True,
                "database": "postgresql",
                "latency_test": "passed" if val == 1 else "failed"
            }
            
        except Exception as e:
            self._connected = False
            LOGGER.error("Database health check failed", extra={"error": str(e)})
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
            }

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected


# Global database client instance
db_client = DatabaseClient(engine)


async def init_database(auto_migrate: bool = True, drop_existing: bool = False) -> None:
    """Initialize database connection and optionally run migrations.
    
    Args:
        auto_migrate: Whether to run auto-migration on startup
        drop_existing: Whether to drop existing tables (WARNING: data loss!)
    """
    try:
        LOGGER.info("Initializing database connection...")
        
        # Test connection
        await db_client.connect()
        
        # Run auto-migration if enabled
        if auto_migrate:
            await db_client.auto_migrate(drop_existing=drop_existing)
        
        LOGGER.info("Database initialization completed")
        
    except Exception as e:
        LOGGER.error(
            "Database initialization failed",
            exc_info=True,
            extra={"error": str(e)}
        )
        raise


async def close_database() -> None:
    """Close database connection."""
    try:
        LOGGER.info("Closing database connection...")
        await db_client.disconnect()
        LOGGER.info("Database connection closed successfully")
    except Exception as e:
        LOGGER.error(
            "Error closing database",
            exc_info=True,
            extra={"error": str(e)}
        )
