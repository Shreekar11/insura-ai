from fastapi import APIRouter
from app.api.v1.endpoints import workflows, documents, users, query
from app.api.v1.middleware.auth import JWTAuthenticationMiddleware

# Create API router
api_router = APIRouter()

# Include routers
api_router.include_router(users.router, prefix="/users", tags=["User"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(query.router, prefix="/query", tags=["Query"])

__all__ = ["api_router"]