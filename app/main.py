"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.api.v1.endpoints import ocr
from app.api.v1.models.ocr import HealthCheckResponse
from app.config import settings
from app.utils.logging import get_logger

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

    yield

    # Shutdown
    LOGGER.info("Shutting down application")


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
    return HealthCheckResponse(
        status="healthy",
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
app.include_router(
    ocr.router,
    prefix=f"{settings.api_v1_prefix}/ocr",
    tags=["OCR"],
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

