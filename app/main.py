"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from uuid import uuid4
from fastapi import FastAPI, APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.api.routes import workflows, health, documents
from app.config import settings
from app.utils.logging import get_logger
from app.database.client import init_database, close_database

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
        LOGGER.info("Initializing database...")
        await init_database(
            auto_migrate=True,
            drop_existing=False 
        )
        LOGGER.info("Database initialized successfully")
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


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Create API router
api_router = APIRouter()
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

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
