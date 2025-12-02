from fastapi import FastAPI, APIRouter

from app.api.routes import workflows, health, documents

api_router = APIRouter()

api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(health.router, prefix="", tags=["Health"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])