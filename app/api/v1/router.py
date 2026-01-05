from fastapi import APIRouter
from app.api.v1.endpoints import workflows, health, documents

# Create API router
api_router = APIRouter()
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

__all__ = ["api_router"]