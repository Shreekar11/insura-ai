"""Centralized dependency injection for FastAPI application.

This module provides factory functions for creating service and repository
instances with proper dependency injection following FastAPI best practices.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_session
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.repositories.ocr_repository import OCRRepository
from app.services.normalization.normalization_service import NormalizationService
from app.services.chunking.chunking_service import ChunkingService
from app.services.classification.classification_service import ClassificationService
from app.services.classification.fallback_classifier import FallbackClassifier
from app.services.ocr.ocr_service import OCRService
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


async def get_normalization_repository(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> NormalizationRepository:
    """Get normalization repository instance.
    
    Args:
        db_session: Database session from dependency injection
        
    Returns:
        NormalizationRepository: Repository for normalization data operations
    """
    return NormalizationRepository(db_session)


async def get_classification_repository(
    db_session: Annotated[AsyncSession, Depends(get_async_session)]
) -> ClassificationRepository:
    """Get classification repository instance.
    
    Args:
        db_session: Database session from dependency injection
        
    Returns:
        ClassificationRepository: Repository for classification data operations
    """
    return ClassificationRepository(db_session)


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


async def get_classification_service() -> ClassificationService:
    """Get classification service instance.
    
    Returns:
        ClassificationService: Service for signal aggregation and classification
    """
    return ClassificationService()


async def get_fallback_classifier() -> FallbackClassifier:
    """Get fallback classifier instance.
    
    Returns:
        FallbackClassifier: Fallback classifier for low-confidence cases
    """
    return FallbackClassifier(
        provider=settings.llm_provider,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_model=settings.openrouter_model,
        openrouter_api_url=settings.openrouter_api_url,
    )



async def get_normalization_service(
    chunk_repository: Annotated[ChunkRepository, Depends(get_chunk_repository)],
    normalization_repository: Annotated[NormalizationRepository, Depends(get_normalization_repository)],
    classification_repository: Annotated[ClassificationRepository, Depends(get_classification_repository)],
    chunking_service: Annotated[ChunkingService, Depends(get_chunking_service)],
    classification_service: Annotated[ClassificationService, Depends(get_classification_service)],
    fallback_classifier: Annotated[FallbackClassifier, Depends(get_fallback_classifier)],
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
) -> NormalizationService:
    """Get normalization service instance with all dependencies.
    
    Args:
        chunk_repository: Repository for chunk operations
        normalization_repository: Repository for normalization operations
        classification_repository: Repository for classification operations
        chunking_service: Service for document chunking
        classification_service: Service for classification
        fallback_classifier: Fallback classifier
        db_session: Database session for extractor factory
        
    Returns:
        NormalizationService: Fully configured normalization service
    """
    # Import here to avoid circular dependency
    from app.services.extraction.extractor_factory import ExtractorFactory
    from app.services.entity.resolver import EntityResolver
    
    # Create extractor factory for section-aware extraction
    extractor_factory = ExtractorFactory(
        session=db_session,
        provider=settings.llm_provider,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_model=settings.openrouter_model,
        openrouter_api_url=settings.openrouter_api_url,
    )
    
    # Create entity resolver for canonical entity resolution
    entity_resolver = EntityResolver(session=db_session)
    
    return NormalizationService(
        provider=settings.llm_provider,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_model=settings.openrouter_model,
        openrouter_api_url=settings.openrouter_api_url,
        enable_llm_fallback=settings.enable_llm_fallback,
        chunking_service=chunking_service,
        classification_service=classification_service,
        fallback_classifier=fallback_classifier,
        chunk_repository=chunk_repository,
        normalization_repository=normalization_repository,
        classification_repository=classification_repository,
        entity_resolver=entity_resolver,
        extractor_factory=extractor_factory,
    )



async def get_ocr_service(
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
    normalization_service: Annotated[NormalizationService, Depends(get_normalization_service)],
) -> OCRService:
    """Get OCR service instance with all dependencies.
    
    Args:
        db_session: Database session
        normalization_service: Normalization service with all dependencies
        
    Returns:
        OCRService: Fully configured OCR service
    """
    return OCRService(
        api_key=settings.mistral_api_key,
        api_url=settings.mistral_api_url,
        model=settings.mistral_model,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        db_session=db_session,
        normalization_service=normalization_service,
        timeout=settings.ocr_timeout,
        max_retries=settings.max_retries,
        retry_delay=settings.retry_delay,
        provider=settings.llm_provider,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_model=settings.openrouter_model,
        openrouter_api_url=settings.openrouter_api_url,
    )
