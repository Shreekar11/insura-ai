"""OCR normalization service for insurance document text cleaning.

This service implements comprehensive text normalization for OCR-extracted
insurance documents using a hybrid LLM + code approach:
- Stage 1: LLM-based structural cleanup (tables, hyphenation, OCR artifacts)
- Stage 2: Deterministic field normalization (dates, amounts, policy numbers)

It also maintains the legacy rule-based approach for backward compatibility.
"""

from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID, uuid4
import hashlib

from app.core.base_service import BaseService
from app.models.page_data import PageData
from app.services.normalization.llm_normalizer import LLMNormalizer
from app.services.normalization.semantic_normalizer import SemanticNormalizer
from app.services.chunking.chunking_service import ChunkingService
from app.services.classification.classification_service import ClassificationService
from app.services.classification.fallback_classifier import FallbackClassifier
from app.services.extraction.entity_relationship_extractor import EntityRelationshipExtractor
from app.services.extraction.entity_resolver import EntityResolver
from app.services.extraction.document_entity_aggregator import DocumentEntityAggregator
from app.services.extraction.relationship_extractor_global import RelationshipExtractorGlobal
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationService(BaseService):
    """Service for normalizing and classifying OCR-extracted insurance documents.
    
    This service uses a hybrid LLM + code approach with chunking and classification:
    1. Chunks pages into manageable segments
    2. Normalizes each chunk using LLM (with signal extraction)
    3. Aggregates classification signals across chunks
    4. Persists chunks, normalized text, and classification to database
    
    The service always uses the hybrid approach with classification enabled.
    
    Attributes:
        llm_normalizer: LLM-based text normalizer with signal extraction
        semantic_normalizer: Semantic field normalizer
        chunking_service: Service for chunking large documents
        classification_service: Service for aggregating classification signals
        fallback_classifier: Fallback classifier for low-confidence cases
        chunk_repository: Repository for chunk CRUD operations
        normalization_repository: Repository for normalization data operations
        classification_repository: Repository for classification data operations
    """

    
    def __init__(
        self,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        enable_llm_fallback: bool = False,        chunking_service: Optional[ChunkingService] = None,
        classification_service: Optional[ClassificationService] = None,
        fallback_classifier: Optional[FallbackClassifier] = None,
        chunk_repository: Optional[ChunkRepository] = None,
        normalization_repository: Optional[NormalizationRepository] = None,
        classification_repository: Optional[ClassificationRepository] = None,
        entity_extractor: Optional[EntityRelationshipExtractor] = None,
        entity_resolver: Optional[EntityResolver] = None,
        extractor_factory: Optional[Any] = None,
    ):
        """Initialize OCR normalization service.
        
        Args:
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key for LLM normalization
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_api_url: OpenRouter API URL
            openrouter_model: OpenRouter model to use
            enable_llm_fallback: Enable fallback to Gemini if OpenRouter fails            chunking_service: Service for chunking large documents
            classification_service: Service for aggregating classification signals
            fallback_classifier: Fallback classifier for low-confidence cases
            chunk_repository: Repository for chunk CRUD operations
            normalization_repository: Repository for normalization data operations
            classification_repository: Repository for classification data operations
            entity_extractor: Entity and relationship extractor
            entity_resolver: Entity resolver for canonical entity mapping
            extractor_factory: Factory for section-specific extractors
        """


        # Initialize BaseService with the primary repository
        super().__init__(repository=normalization_repository)
        
        self.semantic_normalizer = SemanticNormalizer()
        self.chunking_service = chunking_service or ChunkingService()
        self.classification_service = classification_service
        self.fallback_classifier = fallback_classifier
        self.chunk_repository = chunk_repository
        self.normalization_repository = normalization_repository
        self.classification_repository = classification_repository
        self.entity_extractor = entity_extractor
        self.entity_resolver = entity_resolver
        self.extractor_factory = extractor_factory
        
        # Default provider to gemini if not specified
        if not provider:
            provider = "gemini"
        
        # Validate API keys
        if provider == "openrouter" and not openrouter_api_key:
            raise ValueError("OpenRouter provider selected but no API key provided")
        elif provider == "gemini" and not gemini_api_key:
            raise ValueError("Gemini provider selected but no API key provided")
        
        # Initialize LLM normalizer (always required for batch processing)
        self.llm_normalizer = LLMNormalizer(
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model or "gemini-2.0-flash",
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model or "google/gemini-2.0-flash-001",
            openrouter_api_url=openrouter_api_url or "https://openrouter.ai/api/v1/chat/completions",
            enable_fallback=enable_llm_fallback,
        )
        
        # Initialize entity extractor if not provided
        if not self.entity_extractor:
            self.entity_extractor = EntityRelationshipExtractor(
                provider=provider,
                gemini_api_key=gemini_api_key,
                gemini_model=gemini_model or "gemini-2.0-flash",
                openrouter_api_key=openrouter_api_key,
                openrouter_model=openrouter_model or "google/gemini-2.0-flash-001",
                openrouter_api_url=openrouter_api_url or "https://openrouter.ai/api/v1/chat/completions",
            )
        
        # Initialize batch processing components
        from app.services.extraction.batch_extractor import BatchExtractor
        from app.services.normalization.batch_normalization_processor import BatchNormalizationProcessor
        from app.config import settings
        
        # Initialize batch extractor with provider config
        self.unified_extractor = BatchExtractor(
            session=normalization_repository.session if normalization_repository else None,
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model or "gemini-2.0-flash",
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model or "google/gemini-2.0-flash-001",
            openrouter_api_url=openrouter_api_url or "https://openrouter.ai/api/v1/chat/completions",
            batch_size=settings.batch_size,
            timeout=settings.batch_timeout_seconds,
        )
        
        # Initialize batch processor
        if all([chunk_repository, normalization_repository, classification_repository]):
            self.batch_processor = BatchNormalizationProcessor(
                unified_extractor=self.unified_extractor,
                semantic_normalizer=self.semantic_normalizer,
                chunking_service=self.chunking_service,
                entity_resolver=entity_resolver,
                chunk_repository=chunk_repository,
                normalization_repository=normalization_repository,
                classification_repository=classification_repository,
            )
            
            LOGGER.info(
                "Batch processing components initialized",
                extra={"batch_size": settings.batch_size}
            )
        else:
            self.batch_processor = None
        
        # Initialize section batch extractor for optimized section extraction
        from app.services.extraction.section_batch_extractor import SectionBatchExtractor
        
        self.section_batch_extractor = SectionBatchExtractor(
            session=normalization_repository.session if normalization_repository else None,
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model or "gemini-2.0-flash",
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model or "google/gemini-2.0-flash-001",
            openrouter_api_url=openrouter_api_url or "https://openrouter.ai/api/v1/chat/completions",
            timeout=90,
            max_retries=3,
        )
        
        LOGGER.info(
            "Section batch extractor initialized (reduces 3 LLM calls → 1 for sections)",
            extra={"provider": provider}
        )
        
        LOGGER.info(
            "Initialized OCR normalization service with batch processing pipeline",
            extra={
                "llm_provider": provider,
                "llm_model": gemini_model if provider == "gemini" else openrouter_model,
                "has_classification": classification_service is not None,
                "has_chunk_repo": chunk_repository is not None,
                "has_extractor_factory": extractor_factory is not None,
                "batch_processing_enabled": self.batch_processor is not None,
                "fallback_enabled": enable_llm_fallback,
            }
        )
    

    async def normalize_and_classify_pages(
        self,
        pages: List[PageData],
        document_id: UUID,
        max_tokens: int = 1500,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Wrapper for run() to maintain backward compatibility.
        
        Delegates to BaseService.execute().
        """
        return await self.execute(
            pages=pages,
            document_id=document_id,
            max_tokens=max_tokens
        )

    async def run(
        self,
        pages: List[PageData],
        document_id: UUID,
        max_tokens: int = 1500,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Normalize pages and perform document classification.
        
        This method combines normalization with classification by:
        1. Chunking pages if needed
        2. Extracting classification signals during normalization
        3. Persisting chunks and signals to database
        4. Aggregating signals for final classification
        5. Using fallback classification if confidence is low
        
        Args:
            pages: List of PageData objects
            document_id: UUID of the document being processed            max_tokens: Maximum tokens per chunk (default: 1500)
            
        Returns:
            Tuple of (normalized_text, classification_result)
            
        Example:
            >>> service = NormalizationService(...)
            >>> pages = [PageData(...), ...]
            >>> text, classification = await service.normalize_and_classify_pages(pages, doc_id)
            >>> print(classification["classified_type"])  # "policy"
        """
        if not pages:
            LOGGER.warning("Empty pages list provided")
            return "", None
        
        # Feature flag: Use batch processing if enabled
        from app.config import settings
        
        if not self.batch_processor:
             raise ValueError("Batch processor not initialized. Check configuration.")

        LOGGER.info(
            "Starting batch processing pipeline",
            extra={
                "document_id": str(document_id),
                "total_pages": len(pages),
                "batch_size": settings.batch_size
            }
        )
        
        # Use optimized batch processing
        merged_text, classification_result = await self.batch_processor.process_pages_in_batches(
            pages=pages,
            document_id=document_id,
            batch_size=settings.batch_size
        )
        
        # Persist final classification
        if self.classification_repository and classification_result:
            await self.classification_repository.create_document_classification(
                document_id=document_id,
                classified_type=classification_result["classified_type"],
                confidence=classification_result["confidence"],
                classifier_model=classification_result.get("method", "batch_aggregate"),
                decision_details=classification_result,
            )
        
        # Perform document-level extraction (Pass 2)
        await self._process_document_level_extraction(document_id)
        
        LOGGER.info(
            "Batch processing pipeline completed",
            extra={
                "document_id": str(document_id),
                "classified_type": classification_result.get("classified_type") if classification_result else None,
                "confidence": classification_result.get("confidence") if classification_result else None
            }
        )
        
        return merged_text, classification_result
    

    
    def detect_document_sections(self, text: str) -> Dict[str, List[str]]:
        """Detect common insurance document sections.
        
        This method identifies key sections in insurance documents
        which can be useful for downstream classification and extraction.
        
        Args:
            text: Normalized document text
            
        Returns:
            dict: Dictionary mapping section names to line numbers where found
        """
        sections = {
            "declarations": [],
            "endorsements": [],
            "exclusions": [],
            "insuring_agreement": [],
            "schedule_of_values": [],
            "premium_summary": [],
            "loss_history": [],
            "coverages": [],
        }
        
        section_patterns = {
            "declarations": r'\bdeclarations?\b',
            "endorsements": r'\bendorsements?\b',
            "exclusions": r'\bexclusions?\b',
            "insuring_agreement": r'\binsuring agreement\b',
            "schedule_of_values": r'\bschedule of values\b|\bSOV\b',
            "premium_summary": r'\bpremium summary\b',
            "loss_history": r'\bloss (history|runs?)\b',
            "coverages": r'\bcoverages?\b',
        }
        
        lines = text.split('\n')
        for line_num, line in enumerate(lines, start=1):
            line_lower = line.lower()
            for section_name, pattern in section_patterns.items():
                if re.search(pattern, line_lower):
                    sections[section_name].append(line_num)
        
        detected = {k: v for k, v in sections.items() if v}
        
        if detected:
            LOGGER.info(
                "Detected document sections",
                extra={"sections": list(detected.keys())}
            )
        
        return detected
    
    def _generate_stable_chunk_id(
        self,
        document_id: UUID,
        page_number: int,
        chunk_index: int
    ) -> str:
        """Generate deterministic chunk ID.
        
        Format: doc_{document_id}_p{page_number}_c{chunk_index}
        
        Args:
            document_id: Document UUID
            page_number: Page number (1-indexed)
            chunk_index: Chunk index (0-indexed)
            
        Returns:
            str: Stable chunk ID
        """
        return f"doc_{str(document_id)}_p{page_number}_c{chunk_index}"
    
    async def _process_document_level_extraction(
        self,
        document_id: UUID
    ) -> None:
        """Process document-level entity aggregation and relationship extraction (Pass 2).
        
        This method orchestrates the global extraction pipeline:
        1. Aggregate entities from all chunks
        2. Resolve to canonical entities
        3. Extract relationships using global context
        
        Args:
            document_id: Document ID to process
        """
        if not self.entity_resolver:
            LOGGER.warning(
                "Entity resolver not configured, skipping document-level extraction",
                extra={"document_id": str(document_id)}
            )
            return
        
        LOGGER.info(
            "Starting document-level extraction (Pass 2)",
            extra={"document_id": str(document_id)}
        )
        
        try:
            # Step 1: Aggregate entities from all chunks
            aggregator = DocumentEntityAggregator(session=self.repository.session)
            aggregated = await aggregator.aggregate_entities(document_id)
            
            LOGGER.info(
                f"Aggregated {aggregated.unique_entities} unique entities from {aggregated.total_chunks} chunks",
                extra={
                    "document_id": str(document_id),
                    "total_entities": aggregated.total_entities,
                    "unique_entities": aggregated.unique_entities,
                    "deduplication_ratio": f"{(1 - aggregated.unique_entities / max(aggregated.total_entities, 1)) * 100:.1f}%"
                }
            )
            
            # Step 2: Resolve to canonical entities
            resolved = await self.entity_resolver.resolve_entities_batch(
                entities=aggregated.entities,
                chunk_id=None,  # Document-level, not chunk-specific
                document_id=document_id
            )
            
            LOGGER.info(
                f"Resolved {len(resolved)} canonical entities",
                extra={"document_id": str(document_id)}
            )
            
            # Step 3: Extract relationships using global context
            if self.llm_normalizer:  # Only if LLM is available
                relationship_extractor = RelationshipExtractorGlobal(
                    session=self.repository.session,
                    provider=self.llm_normalizer.provider,
                    gemini_api_key=self.llm_normalizer.client.api_key if self.llm_normalizer.provider == "gemini" else None,
                    gemini_model=self.llm_normalizer.client.model if self.llm_normalizer.provider == "gemini" else "gemini-2.0-flash",
                    openrouter_api_key=self.llm_normalizer.client.api_key if self.llm_normalizer.provider == "openrouter" else None,
                    openrouter_model=self.llm_normalizer.client.model if self.llm_normalizer.provider == "openrouter" else "google/gemini-2.0-flash-001",
                )
                
                relationships = await relationship_extractor.extract_relationships(document_id)
                
                LOGGER.info(
                    f"Extracted {len(relationships)} relationships",
                    extra={"document_id": str(document_id)}
                )
            else:
                LOGGER.warning(
                    "LLM not available, skipping relationship extraction",
                    extra={"document_id": str(document_id)}
                )
            
            LOGGER.info(
                "Document-level extraction completed successfully",
                extra={"document_id": str(document_id)}
            )
            
        except Exception as e:
            LOGGER.error(
                f"Document-level extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            # Don't fail the entire pipeline if document-level extraction fails
    

    

    


