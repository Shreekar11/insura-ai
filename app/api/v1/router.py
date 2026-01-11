from fastapi import APIRouter
from app.api.v1.endpoints import workflows, health, documents, users
from app.api.v1.middleware.auth import JWTAuthenticationMiddleware

# Create API router
api_router = APIRouter()

# Add authentication middleware to the router
api_router.add_middleware(JWTAuthenticationMiddleware)

# Include routers
api_router.include_router(users.router, prefix="/users", tags=["User"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

__all__ = ["api_router"]