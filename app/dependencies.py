"""Centralized dependency injection for FastAPI application.

This module provides factory functions for creating service and repository
instances with proper dependency injection following FastAPI best practices.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_session
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.ocr_repository import OCRRepository
from app.services.processed.services.chunking.chunking_service import ChunkingService
from app.services.processed.services.ocr.ocr_service import OCRService
from app.config import settings


async def get_chunk_repository(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ChunkRepository:
    """Get chunk repository instance.
    
    Args:
        db_session: Database session from dependency injection
        
    Returns:
        ChunkRepository: Repository for chunk CRUD operations
    """
    return ChunkRepository(db_session)


async def get_ocr_repository(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> OCRRepository:
    """Get OCR repository instance.
    
    Args:
        db_session: Database session from dependency injection
        
    Returns:
        OCRRepository: Repository for OCR data operations
    """
    return OCRRepository(db_session)


async def get_chunking_service() -> ChunkingService:
    """Get chunking service instance.
    
    Returns:
        ChunkingService: Service for document chunking
    """
    return ChunkingService(
        max_tokens_per_chunk=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
        enable_section_chunking=True,
    )


async def get_ocr_service(
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> OCRService:
    """Get OCR service instance with all dependencies.
    
    Args:
        db_session: Database session
        normalization_service: Normalization service with all dependencies
        
    Returns:
        OCRService: Fully configured OCR service
    """
    return OCRService(
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        db_session=db_session,
        timeout=settings.ocr_timeout,
        max_retries=settings.max_retries,
        retry_delay=settings.retry_delay,
        provider=settings.llm_provider,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_model=settings.openrouter_model,
        openrouter_api_url=settings.openrouter_api_url,
    )
