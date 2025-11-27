"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.api.main import api_router
from app.models.response.response import HealthCheckResponse
from app.config import settings
from app.utils.logging import get_logger
from app.database.client import init_database, close_database, db_client

LOGGER = get_logger(__name__, level=settings.log_level)


class RootResponse(BaseModel):
    """Root endpoint response payload."""

    message: str = Field(..., description="Service status message")
    version: str = Field(..., description="Running application version")
    docs: str = Field(..., description="Path to the interactive API docs")
    health: str = Field(..., description="Path to the health check endpoint")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events for the FastAPI application.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    LOGGER.info(
        "Starting application",
        extra={
            "app_name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
    )
    
    # Initialize database connection and run auto-migration
    try:
        LOGGER.info("Initializing database...")
        await init_database(
            auto_migrate=True,  # Enable auto-migration
            drop_existing=False  # Don't drop existing tables (set to True only for dev reset)
        )
        LOGGER.info("Database initialized successfully")
    except Exception as e:
        LOGGER.error(
            "Failed to initialize database",
            exc_info=True,
            extra={"error": str(e)}
        )
        # Continue startup even if database fails (for development)
        # In production, you might want to raise the exception

    yield

    # Shutdown
    LOGGER.info("Shutting down application")
    
    # Close database connection
    try:
        await close_database()
    except Exception as e:
        LOGGER.error(
            "Error closing database",
            exc_info=True,
            extra={"error": str(e)}
        )



# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered workspace and assistant designed specifically for insurance operations",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["Health"],
    summary="Health check endpoint",
    description="Check if the service is running and healthy",
    operation_id="get_service_health_status",
)
async def health_check() -> HealthCheckResponse:
    """Health check endpoint.

    Returns:
        HealthCheckResponse: Service health status
    """
    # Check database health
    db_health = await db_client.health_check()
    
    return HealthCheckResponse(
        status="healthy" if db_health["status"] == "healthy" else "degraded",
        version=settings.app_version,
        service=settings.app_name,
    )


# Root endpoint
@app.get(
    "/",
    response_model=RootResponse,
    tags=["Root"],
    summary="Root endpoint",
    description="Get basic information about the API",
    operation_id="get_public_root_metadata",
)
async def root() -> RootResponse:
    """Root endpoint.

    Returns:
        RootResponse: Basic API information
    """
    return RootResponse(
        message="Server is running",
        version=settings.app_version,
        docs="/docs",
        health="/health",
    )


# Include routers
app.include_router(api_router, prefix=settings.api_v1_prefix)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

