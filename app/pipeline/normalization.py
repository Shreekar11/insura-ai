"""Phase 2: Normalization facade.

Wraps NormalizationService for chunking and LLM-based normalization.
"""

from typing import List, Dict, Tuple, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.services.entity.resolver import EntityResolver
from app.services.normalization.normalization_service import NormalizationService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationPipeline:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.chunk_repo = ChunkRepository(session)
        self.norm_repo = NormalizationRepository(session)
        self.class_repo = ClassificationRepository(session)
        self.entity_resolver = EntityResolver(session)
        
        self.norm_service = NormalizationService(
            provider=settings.llm_provider,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
            openrouter_api_url=settings.openrouter_api_url,
            openrouter_model=settings.openrouter_model,
            enable_llm_fallback=settings.enable_llm_fallback,
            chunk_repository=self.chunk_repo,
            normalization_repository=self.norm_repo,
            classification_repository=self.class_repo,
            entity_resolver=self.entity_resolver,
        )

    async def process_document(self, document_id: UUID, pages: List[Any]) -> Tuple[List[Dict], Dict]:
        """Run normalization and classification."""
        result, classification = await self.norm_service.run(
            pages=pages,
            document_id=document_id
        )
        return result, classification

