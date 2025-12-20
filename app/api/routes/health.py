"""Health check API endpoints."""

from fastapi import APIRouter
from app.models.response.response import HealthCheckResponse
from app.config import settings
from app.database.client import db_client
from app.utils.logging import get_logger
from temporalio.client import Client
import os

LOGGER = get_logger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    tags=["Health"],
    summary="Health check endpoint",
    description="Check if the service is running and healthy",
    operation_id="get_service_health_status",
)
async def health_check() -> HealthCheckResponse:
    """Health check endpoint."""
    # Check database health
    db_health = await db_client.health_check()
    
    return HealthCheckResponse(
        status="healthy" if db_health["status"] == "healthy" else "degraded",
        version=settings.app_version,
        service=settings.app_name,
    )


@router.get("/health/detailed", tags=["Health"])
async def detailed_health():
    """Detailed health check including dependencies."""
    # Database check
    db_health = await db_client.health_check()
    
    # Temporal check
    temporal_healthy = False
    try:
        temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
        await Client.connect(temporal_host)
        temporal_healthy = True
    except Exception as e:
        LOGGER.warning(f"Temporal health check failed: {e}")

    return {
        "status": "healthy" if db_health["status"] == "healthy" and temporal_healthy else "degraded",
        "database": db_health,
        "temporal": {"status": "healthy" if temporal_healthy else "unhealthy"},
        "version": settings.app_version,
    }
