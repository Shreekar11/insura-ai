"""Section extraction orchestrator for Tier 2 LLM processing.

This service implements the processing:
- Sequential section-level extraction
- Section-specific field extraction using factory pattern
- Batch processing of section super-chunks
- Structured JSON output per section type

Processes sections in priority order using section-specific extractors from factory.
"""

import json
import time
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.processed.services.chunking.hybrid_models import (
    SectionType,
    SectionSuperChunk,
    HybridChunk,
)
from app.services.processed.services.chunking.section_super_chunk_builder import SuperChunkBatch
from app.services.extracted.services.extraction.extractor_factory import ExtractorFactory
from app.services.extracted.services.extraction.section.extractors import (
    DeclarationsExtractor,
    DefinitionsExtractor,
    CoveragesExtractor,
    ConditionsExtractor,
    ExclusionsExtractor,
    EndorsementsExtractor,
    InsuringAgreementExtractor,
    PremiumSummaryExtractor,
    DefaultSectionExtractor,
)
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.step_repository import StepSectionOutputRepository, StepEntityOutputRepository

LOGGER = get_logger(__name__)


@dataclass
class SectionExtractionResult:
    """Result of extracting a single section.
    
    Attributes:
        section_type: Type of section extracted
        extracted_data: Structured data extracted from section
        entities: Entities found in section
        confidence: Extraction confidence
        token_count: Tokens processed
        processing_time_ms: Processing time in milliseconds
    """
    section_type: SectionType
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    token_count: int = 0
    processing_time_ms: int = 0
    extraction_id: Optional[UUID] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "section_type": self.section_type.value,
            "extracted_data": self.extracted_data,
            "entities": self.entities,
            "confidence": self.confidence,
            "token_count": self.token_count,
            "processing_time_ms": self.processing_time_ms,
            "extraction_id": str(self.extraction_id) if self.extraction_id else None,
        }


@dataclass
class DocumentExtractionResult:
    """Complete extraction result for a document.
    
    Attributes:
        document_id: Document ID
        section_results: Results per section
        all_entities: Aggregated entities across sections
        total_tokens: Total tokens processed
        total_processing_time_ms: Total processing time
    """
    document_id: Optional[UUID] = None
    section_results: List[SectionExtractionResult] = field(default_factory=list)
    all_entities: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    total_processing_time_ms: int = 0
    
    def get_section_result(
        self, 
        section_type: SectionType
    ) -> Optional[SectionExtractionResult]:
        """Get result for a specific section."""
        for result in self.section_results:
            if result.section_type == section_type:
                return result
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "section_results": [sr.to_dict() for sr in self.section_results],
            "all_entities": self.all_entities,
            "total_tokens": self.total_tokens,
            "total_processing_time_ms": self.total_processing_time_ms,
        }




class SectionExtractionOrchestrator:
    """Tier 2 orchestrator for section-level extraction.
    
    This service processes section super-chunks sequentially, using
    section-specific extractors from the factory pattern to extract structured data.
    
    Attributes:
        factory: ExtractorFactory for getting section-specific extractors
        session: SQLAlchemy session for persistence
        provider: LLM provider name
        model: LLM model name
    """
    
    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        """Initialize section extraction orchestrator.
        
        Args:
            session: SQLAlchemy async session
            provider: LLM provider
            gemini_api_key: Gemini API key
            gemini_model: Gemini model name
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model name
            openrouter_api_url: OpenRouter API URL
            timeout: API timeout
            max_retries: Max retry attempts
        """
        if not session:
            raise ValueError("session is required for SectionExtractionOrchestrator")
        
        self.session = session
        self.provider = provider
        self.model = gemini_model if provider == "gemini" else openrouter_model
        
        # Initialize extractor factory
        self.factory = ExtractorFactory(
            session=session,
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
            openrouter_api_url=openrouter_api_url,
        )
        
        # Initialize section extraction repository
        self.section_extraction_repo = SectionExtractionRepository(session)
        self.step_section_repo = StepSectionOutputRepository(session)
        self.step_entity_repo = StepEntityOutputRepository(session)
        
        # Register all section extractors with the factory
        self._register_extractors()
        
        LOGGER.info(
            "Initialized SectionExtractionOrchestrator (Tier 2) with factory pattern",
            extra={"provider": provider, "model": self.model}
        )
    
    def _register_extractors(self):
        """Register all section extractors with the factory."""
        # Map SectionType enum values to extractor classes
        extractor_registry = {
            SectionType.DECLARATIONS: DeclarationsExtractor,
            SectionType.DEFINITIONS: DefinitionsExtractor,
            SectionType.COVERAGES: CoveragesExtractor,
            SectionType.CONDITIONS: ConditionsExtractor,
            SectionType.EXCLUSIONS: ExclusionsExtractor,
            SectionType.ENDORSEMENTS: EndorsementsExtractor,
            SectionType.INSURING_AGREEMENT: InsuringAgreementExtractor,
            SectionType.PREMIUM_SUMMARY: PremiumSummaryExtractor,
        }
        
        # Register each extractor with its section type and aliases
        for section_type, extractor_class in extractor_registry.items():
            # Register with enum value
            self.factory.register_extractor(
                section_types=[section_type.value],
                extractor_class=extractor_class
            )
            
            # Register with common aliases
            aliases = self._get_section_aliases(section_type)
            if aliases:
                self.factory.register_extractor(
                    section_types=aliases,
                    extractor_class=extractor_class
                )
        
        # Register default extractor for unknown types
        self.factory.register_extractor(
            section_types=["unknown", "other", "default"],
            extractor_class=DefaultSectionExtractor
        )
        
        LOGGER.debug(
            f"Registered {len(extractor_registry)} section extractors with factory"
        )
    
    def _get_section_aliases(self, section_type: SectionType) -> List[str]:
        """Get common aliases for a section type."""
        alias_map = {
            SectionType.DECLARATIONS: ["declaration", "dec", "policy declarations"],
            SectionType.DEFINITIONS: ["definition", "glossary", "definitions", "policy definitions"],
            SectionType.COVERAGES: ["coverage", "coverages", "insurance coverage"],
            SectionType.CONDITIONS: ["condition", "policy conditions"],
            SectionType.EXCLUSIONS: ["exclusion", "policy exclusions"],
            SectionType.ENDORSEMENTS: ["endorsement", "endorsement forms"],
            SectionType.INSURING_AGREEMENT: ["insuring agreement", "agreement"],
            SectionType.PREMIUM_SUMMARY: ["premium", "premiums", "premium summary"],
        }
        return alias_map.get(section_type, [])
    
    async def run(
        self,
        super_chunks: List[SectionSuperChunk],
        document_id: Optional[UUID] = None,
        workflow_id: Optional[UUID] = None,
    ) -> DocumentExtractionResult:
        """Run section extraction (BaseService compatibility).
        
        Args:
            super_chunks: List of section super-chunks
            document_id: Document ID
            
        Returns:
            DocumentExtractionResult
        """
        return await self.extract_all_sections(super_chunks, document_id, workflow_id)

    async def extract_all_sections(
        self,
        super_chunks: List[SectionSuperChunk],
        document_id: Optional[UUID] = None,
        workflow_id: Optional[UUID] = None,
    ) -> DocumentExtractionResult:
        """Extract data from all section super-chunks.
        
        Processes sections sequentially in priority order.
        
        Args:
            super_chunks: List of section super-chunks
            super_chunks: List of section super-chunks
            document_id: Document ID
            workflow_id: Workflow ID (optional, for step output persistence)
            
        Returns:
            DocumentExtractionResult with all section extractions
        """
        if not super_chunks:
            return DocumentExtractionResult(document_id=document_id)
        
        # Filter to LLM-required sections only
        llm_sections = [sc for sc in super_chunks if sc.requires_llm]
        
        LOGGER.info(
            "Starting section extraction",
            extra={
                "document_id": str(document_id) if document_id else None,
                "total_super_chunks": len(super_chunks),
                "llm_sections": len(llm_sections),
            }
        )
        
        section_results = []
        all_entities = []
        total_tokens = 0
        total_time_ms = 0
        
        # Process sections in priority order
        sorted_sections = sorted(llm_sections, key=lambda sc: sc.processing_priority)
        
        for super_chunk in sorted_sections:
            try:
                result = await self._extract_section(super_chunk, document_id)
                section_results.append(result)
                all_entities.extend(result.entities)
                total_tokens += result.token_count
                total_time_ms += result.processing_time_ms
                
                LOGGER.debug(
                    f"Extracted section: {super_chunk.section_type.value}",
                    extra={
                        "document_id": str(document_id) if document_id else None,
                        "entities_found": len(result.entities),
                        "confidence": result.confidence,
                    }
                )
                
            except Exception as e:
                LOGGER.error(
                    f"Failed to extract section {super_chunk.section_type.value}: {e}",
                    exc_info=True,
                )
                # Add empty result for failed section
                section_results.append(SectionExtractionResult(
                    section_type=super_chunk.section_type,
                    confidence=0.0,
                ))
        
        result = DocumentExtractionResult(
            document_id=document_id,
            section_results=section_results,
            all_entities=all_entities,
            total_tokens=total_tokens,
            total_processing_time_ms=total_time_ms,
        )
        
        LOGGER.info(
            "Section extraction completed",
            extra={
                "document_id": str(document_id) if document_id else None,
                "sections_extracted": len(section_results),
                "total_entities": len(all_entities),
                "total_tokens": total_tokens,
            }
        )
        
        # Persist step outputs if workflow_id is provided
        if workflow_id and document_id:
            await self._persist_step_outputs(result, workflow_id)
        
        return result
    
    async def _persist_step_outputs(
        self,
        result: DocumentExtractionResult,
        workflow_id: UUID,
    ):
        """Persist extraction results to step output tables.
        
        Args:
            result: DocumentExtractionResult
            workflow_id: Workflow ID
        """
        try:
            # Persist section outputs
            for section_res in result.section_results:
                if section_res.confidence == 0.0 and not section_res.extracted_data:
                    continue
                    
                confidence_dict = {
                    "overall": section_res.confidence,
                }
                
                await self.step_section_repo.create(
                    document_id=result.document_id,
                    workflow_id=workflow_id,
                    section_type=section_res.section_type.value,
                    display_payload=section_res.extracted_data,
                    confidence=confidence_dict,
                    page_range=None, # Populate if available in result, but SectionExtractionResult doesn't have it explicitly besides in internal structure
                    source_section_extraction_id=section_res.extraction_id,
                )
                
                # Persist entity outputs for this section
                for entity in section_res.entities:
                    # Entity structure: {"type": "Company", "text": "Name", ...}
                    # We need to map to StepEntityOutput fields
                    entity_type = entity.get("type", "unknown")
                    entity_label = entity.get("text", entity.get("name", "unknown"))
                    
                    await self.step_entity_repo.create(
                        document_id=result.document_id,
                        workflow_id=workflow_id,
                        entity_type=entity_type,
                        entity_label=entity_label,
                        display_payload=entity,
                        confidence=section_res.confidence, # Use section confidence if entity confidence missing
                        source_section_extraction_id=section_res.extraction_id,
                    )
            
            LOGGER.info(
                "Persisted step outputs",
                extra={
                    "document_id": str(result.document_id),
                    "workflow_id": str(workflow_id),
                    "params": {"sections": len(result.section_results)},
                }
            )
            
        except Exception as e:
            LOGGER.error(
                f"Failed to persist step outputs: {e}",
                exc_info=True,
                extra={"document_id": str(result.document_id)}
            )
    
    async def extract_section_batch(
        self,
        batch: SuperChunkBatch,
        document_id: Optional[UUID] = None,
    ) -> List[SectionExtractionResult]:
        """Extract from a batch of super-chunks.
        
        Args:
            batch: SuperChunkBatch to process
            document_id: Document ID
            
        Returns:
            List of SectionExtractionResults
        """
        results = []
        
        for super_chunk in batch.super_chunks:
            try:
                result = await self._extract_section(super_chunk, document_id)
                results.append(result)
            except Exception as e:
                LOGGER.error(f"Batch extraction failed for {super_chunk.section_type}: {e}")
                results.append(SectionExtractionResult(
                    section_type=super_chunk.section_type,
                    confidence=0.0,
                ))
        
        return results
    
    async def _extract_section(
        self,
        super_chunk: SectionSuperChunk,
        document_id: Optional[UUID],
    ) -> SectionExtractionResult:
        """Extract data from a single section super-chunk using factory pattern.
        
        Args:
            super_chunk: Section super-chunk to extract
            document_id: Document ID
            
        Returns:
            SectionExtractionResult
        """
        start_time = time.time()
        
        # Get section-specific extractor from factory
        extractor = self.factory.get_extractor(super_chunk.section_type.value)
        
        # Fallback to default extractor if not found
        if not extractor:
            LOGGER.warning(
                f"No extractor found for section type {super_chunk.section_type.value}, using default",
                extra={"section_type": super_chunk.section_type.value}
            )
            extractor = self.factory.get_extractor("default")
            if not extractor:
                # Create default extractor directly if not registered
                extractor = DefaultSectionExtractor(
                    session=self.session,
                    provider=self.provider,
                    gemini_api_key=self.factory.gemini_api_key,
                    gemini_model=self.factory.gemini_model,
                    openrouter_api_key=self.factory.openrouter_api_key,
                    openrouter_model=self.factory.openrouter_model,
                    openrouter_api_url=self.factory.openrouter_api_url,
                )
        
        # Combine chunk texts
        section_text = super_chunk.get_contextualized_text()
        
        LOGGER.debug(
            f"Extracting section: {super_chunk.section_type.value} using {extractor.__class__.__name__}",
            extra={
                "document_id": str(document_id) if document_id else None,
                "chunk_count": len(super_chunk.chunks),
                "total_tokens": super_chunk.total_tokens,
                "extractor_class": extractor.__class__.__name__,
            }
        )
        
        try:
            # Use extractor's LLM client to call API
            response = await extractor.client.generate_content(
                contents=f"Extract from this {super_chunk.section_type.value} section:\n\n{section_text}",
                system_instruction=extractor.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            parsed = parse_json_safely(response)
            
            if parsed is None:
                LOGGER.warning(f"Failed to parse extraction response for {super_chunk.section_type}")
                parsed = {}
            
            # Extract fields using extractor's method
            if hasattr(extractor, 'extract_fields'):
                extracted_data = extractor.extract_fields(parsed)
            else:
                # Fallback to old method
                extracted_data = self._extract_section_data(parsed, super_chunk.section_type)
            
            entities = parsed.get("entities", [])
            confidence = float(parsed.get("confidence", 0.0))
            
            processing_time = int((time.time() - start_time) * 1000)
            
            extraction_id = None
            
            # Persist section extraction to database
            if document_id:
                try:
                    # Build source_chunks reference from super_chunk
                    source_chunks = {
                        "chunk_ids": [],
                        "stable_chunk_ids": [],
                        "page_range": super_chunk.page_range,
                    }
                    
                    # Extract chunk IDs from super_chunk chunks
                    for chunk in super_chunk.chunks:
                        if chunk.metadata.stable_chunk_id:
                            source_chunks["stable_chunk_ids"].append(chunk.metadata.stable_chunk_id)
                    
                    # Build page_range dict
                    page_range_dict = None
                    if super_chunk.page_range:
                        page_range_dict = {
                            "start": min(super_chunk.page_range),
                            "end": max(super_chunk.page_range),
                        }
                    
                    # Build confidence dict
                    confidence_dict = None
                    if confidence > 0:
                        confidence_dict = {
                            "overall": confidence,
                            "section_type": super_chunk.section_type.value,
                        }
                    
                    # Include entities in extracted_fields so they can be retrieved later
                    extracted_fields_with_entities = {
                        **extracted_data,
                        "entities": entities  # Store entities for entity aggregation
                    }
                    
                    extraction = await self.section_extraction_repo.create_section_extraction(
                        document_id=document_id,
                        section_type=super_chunk.section_type.value,
                        extracted_fields=extracted_fields_with_entities,
                        page_range=page_range_dict,
                        confidence=confidence_dict,
                        source_chunks=source_chunks if source_chunks["stable_chunk_ids"] else None,
                        model_version=self.model,
                        prompt_version="v1",
                    )
                    extraction_id = extraction.id
                    
                    LOGGER.debug(
                        "Persisted section extraction",
                        extra={
                            "document_id": str(document_id),
                            "section_type": super_chunk.section_type.value,
                        }
                    )
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to persist section extraction: {e}",
                        exc_info=True,
                        extra={
                            "document_id": str(document_id),
                            "section_type": super_chunk.section_type.value,
                        }
                    )
            
            return SectionExtractionResult(
                section_type=super_chunk.section_type,
                extracted_data=extracted_data,
                entities=entities,
                confidence=confidence,
                token_count=super_chunk.total_tokens,
                processing_time_ms=processing_time,
                extraction_id=extraction_id,
            )
            
        except Exception as e:
            LOGGER.error(
                f"Section extraction failed: {e}",
                exc_info=True,
                extra={
                    "section_type": super_chunk.section_type.value,
                    "extractor_class": extractor.__class__.__name__,
                }
            )
            raise
    
    def _extract_section_data(
        self,
        parsed: Dict[str, Any],
        section_type: SectionType,
    ) -> Dict[str, Any]:
        """Extract section-specific data from parsed response.
        
        Args:
            parsed: Parsed JSON response
            section_type: Section type
            
        Returns:
            Extracted data dictionary
        """
        # Different sections have different response structures
        if section_type == SectionType.DECLARATIONS:
            return parsed.get("fields", parsed)
        elif section_type == SectionType.COVERAGES:
            return {"coverages": parsed.get("coverages", [])}
        elif section_type == SectionType.CONDITIONS:
            return {"conditions": parsed.get("conditions", [])}
        elif section_type == SectionType.EXCLUSIONS:
            return {"exclusions": parsed.get("exclusions", [])}
        elif section_type == SectionType.ENDORSEMENTS:
            return {"endorsements": parsed.get("endorsements", [])}
        elif section_type == SectionType.INSURING_AGREEMENT:
            return parsed.get("insuring_agreement", parsed)
        elif section_type == SectionType.PREMIUM_SUMMARY:
            return parsed.get("premium", parsed)
        else:
            return parsed.get("extracted_data", parsed)
    
    async def extract_single_section_type(
        self,
        chunks: List[HybridChunk],
        section_type: SectionType,
        document_id: Optional[UUID] = None,
    ) -> SectionExtractionResult:
        """Extract from chunks of a specific section type.
        
        Convenience method when you have chunks but not a super-chunk.
        
        Args:
            chunks: List of hybrid chunks
            section_type: Section type
            document_id: Document ID
            
        Returns:
            SectionExtractionResult
        """
        # Create temporary super-chunk
        super_chunk = SectionSuperChunk(
            section_type=section_type,
            section_name=section_type.value.replace("_", " ").title(),
            chunks=chunks,
            document_id=document_id,
        )
        
        return await self._extract_section(super_chunk, document_id)

