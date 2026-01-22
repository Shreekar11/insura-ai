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
    PremiumExtractor,
    DeductiblesExtractor,
    DefaultSectionExtractor,
    EndorsementCoverageProjectionExtractor,
    EndorsementExclusionProjectionExtractor,
)
from app.models.page_analysis_models import SemanticRole
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


# Batching thresholds for section extraction
# If a section exceeds these, it will be processed in batches
BATCH_TOKEN_THRESHOLD = 3000
BATCH_CHUNK_THRESHOLD = 5


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
            SectionType.PREMIUM_SUMMARY: PremiumExtractor,
            SectionType.PREMIUM: PremiumExtractor,
            SectionType.DEDUCTIBLES: DeductiblesExtractor,
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
        
        # Register projection extractors
        self.factory.register_extractor(
            section_types=["endorsement_coverage_projection"],
            extractor_class=EndorsementCoverageProjectionExtractor
        )
        self.factory.register_extractor(
            section_types=["endorsement_exclusion_projection"],
            extractor_class=EndorsementExclusionProjectionExtractor
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
            SectionType.PREMIUM: ["premium", "premiums", "premium summary"],
            SectionType.DEDUCTIBLES: ["deductible", "deductibles", "retention", "sir"],
        }
        return alias_map.get(section_type, [])
    
    async def run(
        self,
        super_chunks: List[SectionSuperChunk],
        workflow_id: UUID,
        document_id: UUID,
    ) -> DocumentExtractionResult:
        """Run section extraction (BaseService compatibility).
        
        Args:
            super_chunks: List of section super-chunks
            workflow_id: Workflow ID
            document_id: Document ID
            
        Returns:
            DocumentExtractionResult
        """
        return await self.extract_all_sections(super_chunks, workflow_id, document_id)

    async def extract_all_sections(
        self,
        super_chunks: List[SectionSuperChunk],
        workflow_id: UUID,
        document_id: UUID,
    ) -> DocumentExtractionResult:
        """Extract data from all section super-chunks.
        
        Processes sections sequentially in priority order.
        
        Args:
            super_chunks: List of section super-chunks
            workflow_id: Workflow ID
            document_id: Document ID
            
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
                "workflow_id": str(workflow_id),
                "document_id": str(document_id),
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
            # TERMINAL GUARD: Never extract from certificates in coverage pipeline
            if super_chunk.section_type == SectionType.CERTIFICATE_OF_INSURANCE:
                LOGGER.info(f"Skipping extraction for certificate section on pages {super_chunk.page_range}")
                continue

            try:
                result = await self._extract_section(super_chunk, document_id, workflow_id)
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

        # Persist extraction results
        if workflow_id and document_id:
            await self._persist_step_outputs(result, workflow_id)
        
        LOGGER.info(
            "Section extraction completed",
            extra={
                "document_id": str(document_id) if document_id else None,
                "sections_extracted": len(section_results),
                "total_entities": len(all_entities),
                "total_tokens": total_tokens,
            }
        )
        
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
                    section_type=section_res.section_type,
                    display_payload=section_res.extracted_data,
                    confidence=confidence_dict,
                    page_range=None,
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
                        confidence=section_res.confidence,
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
        
    async def _extract_section(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a single section super-chunk.
        
        Decides between single-call or batched extraction based on size.
        
        Args:
            super_chunk: Section super-chunk to extract
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult
        """
        # Determine if batching is needed
        if (super_chunk.total_tokens > BATCH_TOKEN_THRESHOLD or 
            len(super_chunk.chunks) > BATCH_CHUNK_THRESHOLD):
            LOGGER.info(
                f"Section {super_chunk.section_type.value} exceeds thresholds "
                f"({super_chunk.total_tokens} tokens, {len(super_chunk.chunks)} chunks), "
                f"using batched extraction",
                extra={
                    "section_type": super_chunk.section_type.value,
                    "tokens": super_chunk.total_tokens,
                    "chunks": len(super_chunk.chunks),
                }
            )
            return await self._extract_section_batched(super_chunk, document_id, workflow_id)
        
        return await self._extract_section_single(super_chunk, document_id, workflow_id)

    async def _extract_section_single(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a single section super-chunk using factory pattern.
        
        Args:
            super_chunk: Section super-chunk to extract
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult
        """
        start_time = time.time()
        
        # Determine if we should use a projection extractor based on semantic role
        # Check first chunk's metadata for semantic role if available
        extractor_key = super_chunk.section_type.value
        
        if super_chunk.chunks:
            metadata = super_chunk.chunks[0].metadata
            from app.models.page_analysis_models import SemanticRole
            
            # Check for Endorsement Coverage Projection
            if (metadata.original_section_type == SectionType.ENDORSEMENTS and 
                metadata.effective_section_type == SectionType.COVERAGES and
                metadata.semantic_role == SemanticRole.COVERAGE_MODIFIER):
                extractor_key = "endorsement_coverage_projection"
                LOGGER.info(
                    f"Routing to EndorsementCoverageProjectionExtractor for section on pages {super_chunk.page_range}"
                )
            
            # Check for Endorsement Exclusion Projection
            elif (metadata.original_section_type == SectionType.ENDORSEMENTS and 
                  metadata.effective_section_type == SectionType.EXCLUSIONS and
                  metadata.semantic_role == SemanticRole.EXCLUSION_MODIFIER):
                extractor_key = "endorsement_exclusion_projection"
                LOGGER.info(
                    f"Routing to EndorsementExclusionProjectionExtractor for section on pages {super_chunk.page_range}"
                )
        
        # Get section-specific extractor from factory
        extractor = self.factory.get_extractor(extractor_key)
        
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
            # Use helper to run extraction call
            parsed = await self._run_extraction_call(extractor, super_chunk)
            
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
            if document_id and workflow_id:
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
                        workflow_id=workflow_id,
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
                            "workflow_id": str(workflow_id),
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

    async def _run_extraction_call(
        self,
        extractor: Any,
        super_chunk: SectionSuperChunk,
    ) -> Dict[str, Any]:
        """Run a single LLM extraction call.
        
        Args:
            extractor: The section extractor to use
            super_chunk: Super-chunk or batch sub-chunk
            
        Returns:
            Parsed JSON dictionary
        """
        section_text = super_chunk.get_contextualized_text()
        
        response = await extractor.client.generate_content(
            contents=f"Extract from this {super_chunk.section_type.value} section:\n\n{section_text}",
            system_instruction=extractor.get_extraction_prompt(),
            generation_config={"response_mime_type": "application/json"}
        )
        
        return parse_json_safely(response)

    async def _extract_section_batched(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a section in multiple batches.
        
        Args:
            super_chunk: Large section super-chunk to extract
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult (aggregated)
        """
        start_time = time.time()
        
        # Determine extractor to use (same logic as single extraction)
        extractor_key = super_chunk.section_type.value
        if super_chunk.chunks:
            metadata = super_chunk.chunks[0].metadata
            if (metadata.original_section_type == SectionType.ENDORSEMENTS and 
                metadata.effective_section_type == SectionType.COVERAGES and
                metadata.semantic_role == SemanticRole.COVERAGE_MODIFIER):
                extractor_key = "endorsement_coverage_projection"
            elif (metadata.original_section_type == SectionType.ENDORSEMENTS and 
                  metadata.effective_section_type == SectionType.EXCLUSIONS and
                  metadata.semantic_role == SemanticRole.EXCLUSION_MODIFIER):
                extractor_key = "endorsement_exclusion_projection"

        extractor = self.factory.get_extractor(extractor_key) or self.factory.get_extractor("default")
        
        # Split chunks into batches
        chunk_batches = []
        current_batch = []
        current_tokens = 0
        
        for chunk in super_chunk.chunks:
            if current_batch and (current_tokens + chunk.metadata.token_count > BATCH_TOKEN_THRESHOLD or 
                                len(current_batch) >= BATCH_CHUNK_THRESHOLD):
                chunk_batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            current_batch.append(chunk)
            current_tokens += chunk.metadata.token_count
            
        if current_batch:
            chunk_batches.append(current_batch)
            
        LOGGER.info(f"Split section {super_chunk.section_type.value} into {len(chunk_batches)} batches")
        
        parsed_results = []
        total_input_tokens = 0
        
        for i, batch in enumerate(chunk_batches):
            batch_super_chunk = SectionSuperChunk(
                section_type=super_chunk.section_type,
                section_name=super_chunk.section_name,
                chunks=batch,
                document_id=document_id,
            )
            
            try:
                LOGGER.debug(f"Processing batch {i+1}/{len(chunk_batches)} for {super_chunk.section_type.value}")
                parsed = await self._run_extraction_call(extractor, batch_super_chunk)
                if parsed:
                    parsed_results.append(parsed)
                total_input_tokens += batch_super_chunk.total_tokens
            except Exception as e:
                LOGGER.error(f"Batch {i+1} failed for {super_chunk.section_type.value}: {e}")
        
        if not parsed_results:
            return SectionExtractionResult(section_type=super_chunk.section_type)
            
        # Aggregate results
        aggregated_parsed = self._aggregate_batch_results(parsed_results, super_chunk.section_type)
        
        # Extract fields using extractor
        if hasattr(extractor, 'extract_fields'):
            extracted_data = extractor.extract_fields(aggregated_parsed)
        else:
            extracted_data = self._extract_section_data(aggregated_parsed, super_chunk.section_type)
            
        entities = aggregated_parsed.get("entities", [])
        confidence = float(aggregated_parsed.get("confidence", 0.0))
        
        processing_time = int((time.time() - start_time) * 1000)
        
        # Persist (similar to single extraction logic)
        extraction_id = None
        if document_id and workflow_id:
            # Aggregate stable chunk IDs from all chunks
            all_stable_ids = [c.metadata.stable_chunk_id for c in super_chunk.chunks if c.metadata.stable_chunk_id]
            
            source_chunks = {
                "chunk_ids": [],
                "stable_chunk_ids": all_stable_ids,
                "page_range": super_chunk.page_range,
            }
            
            page_range_dict = None
            if super_chunk.page_range:
                page_range_dict = {"start": min(super_chunk.page_range), "end": max(super_chunk.page_range)}
            
            confidence_dict = {"overall": confidence, "section_type": super_chunk.section_type.value} if confidence > 0 else None
            
            extracted_fields_with_entities = {**extracted_data, "entities": entities}
            
            try:
                extraction = await self.section_extraction_repo.create_section_extraction(
                    document_id=document_id,
                    workflow_id=workflow_id,
                    section_type=super_chunk.section_type.value,
                    extracted_fields=extracted_fields_with_entities,
                    page_range=page_range_dict,
                    confidence=confidence_dict,
                    source_chunks=source_chunks if all_stable_ids else None,
                    model_version=self.model,
                    prompt_version="v1_batched",
                )
                extraction_id = extraction.id
            except Exception as e:
                LOGGER.warning(f"Failed to persist batched section extraction: {e}")

        return SectionExtractionResult(
            section_type=super_chunk.section_type,
            extracted_data=extracted_data,
            entities=entities,
            confidence=confidence,
            token_count=total_input_tokens,
            processing_time_ms=processing_time,
            extraction_id=extraction_id,
        )

    def _aggregate_batch_results(
        self,
        parsed_results: List[Dict[str, Any]],
        section_type: SectionType,
    ) -> Dict[str, Any]:
        """Aggregate results from multiple extraction batches.
        
        Args:
            parsed_results: List of parsed JSON records from LLM calls
            section_type: The section type
            
        Returns:
            Single aggregated dictionary
        """
        if not parsed_results:
            return {}
            
        if len(parsed_results) == 1:
            return parsed_results[0]
            
        aggregated = {
            "entities": [],
            "confidence": 0.0,
        }
        
        # List items to aggregate for specific section types
        list_keys = {
            SectionType.COVERAGES: "coverages",
            SectionType.CONDITIONS: "conditions",
            SectionType.EXCLUSIONS: "exclusions",
            SectionType.ENDORSEMENTS: "endorsements",
            SectionType.DEDUCTIBLES: "deductibles",
            SectionType.DEFINITIONS: "definitions",
        }
        
        target_list_key = list_keys.get(section_type)
        if target_list_key:
            aggregated[target_list_key] = []
            
        confidences = []
        
        for res in parsed_results:
            # Aggregate entities
            if "entities" in res and isinstance(res["entities"], list):
                aggregated["entities"].extend(res["entities"])
            
            # Aggregate specific lists
            if target_list_key and target_list_key in res and isinstance(res[target_list_key], list):
                aggregated[target_list_key].extend(res[target_list_key])
            elif not target_list_key:
                # For non-list sections, we might have nested fields or keys
                # e.g. Declarations. We merge top-level keys if they don't exist.
                # If target_list_key is None, we try to merge 'fields' or other keys
                for k, v in res.items():
                    if k not in ["entities", "confidence"]:
                        if k not in aggregated:
                            aggregated[k] = v
                        elif isinstance(aggregated[k], list) and isinstance(v, list):
                            aggregated[k].extend(v)
                        elif isinstance(aggregated[k], dict) and isinstance(v, dict):
                            aggregated[k].update(v)
            
            # Collect confidence
            if "confidence" in res:
                try:
                    confidences.append(float(res["confidence"]))
                except (ValueError, TypeError):
                    pass
        
        # Average confidence
        if confidences:
            aggregated["confidence"] = sum(confidences) / len(confidences)
            
        return aggregated

    
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
        elif section_type == SectionType.PREMIUM_SUMMARY or section_type == SectionType.PREMIUM:
            return parsed.get("premium", parsed)
        elif section_type == SectionType.DEDUCTIBLES:
            return {"deductibles": parsed.get("deductibles", [])}
        else:
            return parsed.get("extracted_data", parsed)
    
    async def extract_single_section_type(
        self,
        chunks: List[HybridChunk],
        section_type: SectionType,
        document_id: Optional[UUID] = None,
        workflow_id: Optional[UUID] = None,
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
        
        return await self._extract_section(super_chunk, document_id, workflow_id)

