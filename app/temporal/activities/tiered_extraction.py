"""Phase 4: Tiered LLM Extraction activities.

These activities handle the three-tier LLM extraction pipeline:
- Tier 1: Document classification and section mapping
- Tier 2: Section-level field extraction
- Tier 3: Cross-section validation and reconciliation
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from app.database.base import async_session_maker
from app.services.extraction.document import DocumentClassificationService
from app.services.extraction.section import (
    SectionExtractionOrchestrator,
    CrossSectionValidator,
)
from app.services.pipeline.section_batch_extractor import SectionBatchExtractor
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_section_type(section_type_str: Optional[str]) -> str:
    """Normalize section type string to valid SectionType enum value.
    
    Maps alternative section type strings to their canonical SectionType values.
    For example, "sov" maps to "schedule_of_values", "endorsement" maps to "endorsements".
    
    Args:
        section_type_str: Section type string to normalize (can be None)
        
    Returns:
        Normalized section type string that matches a SectionType enum value
    """
    if not section_type_str:
        return "unknown"
    
    # Map of alternative names to canonical SectionType values
    section_type_mapping = {
        # Schedule of Values variations
        "sov": "schedule_of_values",
        "schedule_of_values": "schedule_of_values",
        
        # Endorsement variations (singular -> plural)
        "endorsement": "endorsements",
        "endorsements": "endorsements",
        
        # Definitions is not in SectionType enum - map to unknown
        "definitions": "unknown",
    }
    
    normalized = section_type_mapping.get(section_type_str.lower(), section_type_str.lower())
    return normalized


@activity.defn
async def classify_document_and_map_sections(document_id: str) -> Dict:
    """Tier 1: Classify document type and map section boundaries.
    
    This activity:
    1. Retrieves initial pages (typically first 5-10 pages)
    2. Uses LLM to classify document type
    3. Maps section boundaries across the document
    4. Persists classification results
    
    Args:
        document_id: UUID of the document to classify
        
    Returns:
        Dictionary with classification results and section map
    """
    try:
        activity.logger.info(
            f"[Phase 4 - Tier 1] Starting document classification for: {document_id}"
        )
        activity.heartbeat("Starting document classification")
        
        async with async_session_maker() as session:
            # Fetch initial pages for classification (first 10 pages)
            doc_repo = DocumentRepository(session)
            all_pages = await doc_repo.get_pages_by_document(UUID(document_id))
            
            if not all_pages:
                raise ValueError(f"No pages found for document {document_id}")
            
            # Use first 10 pages for classification
            initial_pages = all_pages[:10]
            
            activity.logger.info(
                f"[Phase 4 - Tier 1] Using {len(initial_pages)} initial pages for classification"
            )
            activity.heartbeat(f"Analyzing {len(initial_pages)} pages")
            
            # Perform classification
            classification_service = DocumentClassificationService(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                # ollama_model="deepseek-r1:7b",
            )
            
            classification_result = await classification_service.run(
                pages=initial_pages,
                document_id=UUID(document_id)
            )
            
            await session.commit()
            
            activity.logger.info(
                f"[Phase 4 - Tier 1] Classification complete: "
                f"type={classification_result.document_type}, "
                f"subtype={classification_result.document_subtype}, "
                f"sections={len(classification_result.section_boundaries)}"
            )
            
            return classification_result.to_dict()
            
    except Exception as e:
        activity.logger.error(
            f"Document classification failed for {document_id}: {e}",
            exc_info=True
        )
        raise


@activity.defn
async def extract_section_fields(document_id: str, classification_result: Dict) -> Dict:
    """Tier 2: Extract section-specific fields from super-chunks.
    
    This activity:
    1. Retrieves section super-chunks from database
    2. Orchestrates section-level extraction using LLM
    3. Aggregates entities across chunks
    4. Persists extracted data
    
    Args:
        document_id: UUID of the document to extract from
        classification_result: Classification result from Tier 1
        
    Returns:
        Dictionary with extraction results
    """
    try:
        activity.logger.info(
            f"[Phase 4 - Tier 2] Starting section extraction for: {document_id}"
        )
        activity.heartbeat("Starting section extraction")
        
        async with async_session_maker() as session:
            # Fetch section super-chunks
            chunk_repo = SectionChunkRepository(session)
            super_chunks = await chunk_repo.rebuild_super_chunks(UUID(document_id))
            
            if not super_chunks:
                raise ValueError(f"No super-chunks found for document {document_id}")
            
            activity.logger.info(
                f"[Phase 4 - Tier 2] Retrieved {len(super_chunks)} super-chunks for extraction"
            )
            activity.heartbeat(f"Processing {len(super_chunks)} super-chunks")
            
            # Initialize section batch extractor (reused component)
            section_batch_extractor = SectionBatchExtractor(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                # ollama_model=settings.ollama_model,
            )
            
            # Initialize extraction orchestrator
            extraction_orchestrator = SectionExtractionOrchestrator(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                # ollama_model=settings.ollama_model,
            )
            
            # Perform extraction
            extraction_result = await extraction_orchestrator.run(
                super_chunks=super_chunks,
                document_id=UUID(document_id)
            )
            
            await session.commit()
            
            activity.logger.info(
                f"[Phase 4 - Tier 2] Section extraction complete: "
                f"{len(extraction_result.section_results)} sections processed, "
                f"{len(extraction_result.all_entities)} entities extracted"
            )
            
            return extraction_result.to_dict()
            
    except Exception as e:
        activity.logger.error(
            f"Section extraction failed for {document_id}: {e}",
            exc_info=True
        )
        raise


@activity.defn
async def validate_and_reconcile_data(
    document_id: str,
    classification_result: Dict,
    extraction_result: Dict
) -> Dict:
    """Tier 3: Cross-section validation and data reconciliation.
    
    This activity:
    1. Validates extracted data across sections
    2. Reconciles conflicting values
    3. Identifies data quality issues
    4. Produces final validated dataset
    
    Args:
        document_id: UUID of the document
        classification_result: Classification result from Tier 1
        extraction_result: Extraction result from Tier 2
        
    Returns:
        Dictionary with validation results
    """
    try:
        activity.logger.info(
            f"[Phase 4 - Tier 3] Starting cross-section validation for: {document_id}"
        )
        activity.heartbeat("Starting validation")
        
        async with async_session_maker() as session:
            # Reconstruct classification result
            from app.services.extraction.document import DocumentClassificationResult, SectionBoundary
            from app.services.chunking.hybrid_models import SectionType
            
            section_boundaries = []
            for sb in classification_result["section_boundaries"]:
                try:
                    # Normalize section type string before creating enum
                    section_type_value = sb.get("section_type") or "unknown"
                    section_type_str = _normalize_section_type(section_type_value)
                    section_type = SectionType(section_type_str)
                except (ValueError, KeyError) as e:
                    logger.warning(
                        f"Invalid section type '{sb.get('section_type')}', using UNKNOWN: {e}"
                    )
                    section_type = SectionType.UNKNOWN
                
                section_boundaries.append(
                    SectionBoundary(
                        section_type=section_type,
                        start_page=sb["start_page"],
                        end_page=sb["end_page"],
                        confidence=sb["confidence"],
                        anchor_text=sb.get("anchor_text")
                    )
                )
            
            classification_obj = DocumentClassificationResult(
                document_type=classification_result["document_type"],
                document_id=document_id,
                document_subtype=classification_result.get("document_subtype"),
                confidence=classification_result["confidence"],
                section_boundaries=section_boundaries,
                metadata=classification_result.get("metadata", {})
            )
            
            # Reconstruct extraction result
            from app.services.extraction.section import DocumentExtractionResult, SectionExtractionResult
            
            section_results = []
            for sr in extraction_result["section_results"]:
                try:
                    # Normalize section type string before creating enum
                    section_type_value = sr.get("section_type") or "unknown"
                    section_type_str = _normalize_section_type(section_type_value)
                    section_type = SectionType(section_type_str)
                except (ValueError, KeyError) as e:
                    logger.warning(
                        f"Invalid section type '{sr.get('section_type')}', using UNKNOWN: {e}"
                    )
                    section_type = SectionType.UNKNOWN
                
                section_results.append(
                    SectionExtractionResult(
                        section_type=section_type,
                        extracted_data=sr["extracted_data"],
                        entities=sr["entities"],
                        confidence=sr["confidence"],
                        token_count=sr["token_count"],
                        processing_time_ms=sr["processing_time_ms"]
                    )
                )
            
            extraction_obj = DocumentExtractionResult(
                document_id=document_id,
                section_results=section_results,
                all_entities=extraction_result.get("all_entities", []),
                total_tokens=extraction_result.get("total_tokens", 0),
                total_processing_time_ms=extraction_result.get("total_processing_time_ms", 0)
            )
            
            # Perform validation
            validator = CrossSectionValidator(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
                # ollama_model=settings.ollama_model,
                # ollama_api_url=settings.ollama_api_url,
            )
            
            validation_result = await validator.validate(
                extraction_result=extraction_obj
            )
            
            await session.commit()
            
            activity.logger.info(
                f"[Phase 4 - Tier 3] Validation complete: "
                f"{len(validation_result.issues)} issues found"
            )
            
            return validation_result.to_dict()
            
    except Exception as e:
        activity.logger.error(
            f"Validation failed for {document_id}: {e}",
            exc_info=True
        )
        raise

