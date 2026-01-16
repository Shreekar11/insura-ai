"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from uuid import uuid4
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.utils.logging import get_logger
from app.core.database import init_database, close_database
from app.core.neo4j_client import init_neo4j
from app.api.v1.middleware.auth import JWTAuthenticationMiddleware

LOGGER = get_logger(__name__, level=settings.log_level)


class RootResponse(BaseModel):
    """Root endpoint response payload."""

    message: str = Field(..., description="Service status message")
    version: str = Field(..., description="Running application version")
    docs: str = Field(..., description="Path to the interactive API docs")
    health: str = Field(..., description="Path to the health check endpoint")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    LOGGER.info("Validating configuration...")
    if not settings.gemini_api_key:
        LOGGER.error("GEMINI_API_KEY is missing")

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
        # Check if this is a reload using parent process ID (uvicorn watcher)
        ppid = os.getppid()
        lock_file = f"/tmp/insura_ai_init_{ppid}.lock"
        should_initialize = not os.path.exists(lock_file)
        
        if should_initialize:
            LOGGER.info(f"First startup detected (PPID: {ppid}), running migrations...")
            # Create lock file to indicate initialization happened
            try:
                with open(lock_file, "w") as f:
                    f.write("initialized")
            except Exception as e:
                LOGGER.warning(f"Failed to create init lock file: {e}")
        else:
            LOGGER.info(f"Reload detected (PPID: {ppid}), skipping migrations...")

        LOGGER.info("Initializing database...")
        await init_database(
            auto_migrate=should_initialize,
            drop_existing=False 
        )
        LOGGER.info("Database initialized successfully")

        await init_neo4j(ensure_constraints=should_initialize)
        LOGGER.info("Neo4j initialized successfully")
    except Exception as e:
        LOGGER.error(
            "Failed to initialize database",
            exc_info=True,
            extra={"error": str(e)}
        )

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

# CORD middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Correlation ID middleware
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# JWT authentication middleware
app.add_middleware(JWTAuthenticationMiddleware)

# Include routers
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(health.router, prefix="/health", tags=["Health"])

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
