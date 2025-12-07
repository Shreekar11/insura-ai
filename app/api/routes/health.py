"""Health check API endpoints."""

from fastapi import APIRouter
from app.models.response.response import HealthCheckResponse
from app.config import settings
from app.database.client import db_client
from app.utils.logging import get_logger

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
