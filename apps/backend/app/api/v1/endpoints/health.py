"""Health check API endpoints."""

from fastapi import APIRouter, Request
from app.core.config import settings
from app.core.database import db_client
from app.utils.logging import get_logger
from app.schemas.generated.health import HealthCheckResponse, ApiResponse
from app.utils.responses import create_api_response

LOGGER = get_logger(__name__)

router = APIRouter()

@router.get(
    "/",
    response_model=ApiResponse,
    tags=["Health"],
    summary="Health check endpoint",
    description="Check if the service is running and healthy",
    operation_id="get_service_health_status",
)
async def health_check(request: Request) -> ApiResponse:
    """Health check endpoint."""
    # Check database health
    db_health = await db_client.health_check()
    
    data = HealthCheckResponse(
        status="healthy" if db_health["status"] == "healthy" else "degraded",
        version=settings.app_version,
        service=settings.app_name,
    )
    
    return create_api_response(
        data=data,
        message="Service health status retrieved successfully",
        request=request
    )
