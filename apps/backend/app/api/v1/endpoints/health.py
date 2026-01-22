"""Health check API endpoints."""

from fastapi import APIRouter
from app.core.config import settings
from app.core.database import db_client
from app.utils.logging import get_logger
from temporalio.client import Client
import os

from pydantic import BaseModel, Field

LOGGER = get_logger(__name__)

router = APIRouter()

class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="Health check status")
    version: str = Field(..., description="Running application version")
    service: str = Field(..., description="Service name")

@router.get(
    "/",
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

