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
from app.services.extracted.services.synthesis import SynthesisOrchestrator

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
        effective_coverages: Synthesized coverage-centric output
        effective_exclusions: Synthesized exclusion-centric output
        synthesis_metadata: Metadata about synthesis process
    """
    document_id: Optional[UUID] = None
    section_results: List[SectionExtractionResult] = field(default_factory=list)
    all_entities: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    total_processing_time_ms: int = 0
    effective_coverages: List[Dict[str, Any]] = field(default_factory=list)
    effective_exclusions: List[Dict[str, Any]] = field(default_factory=list)
    synthesis_metadata: Dict[str, Any] = field(default_factory=dict)

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
            "effective_coverages": self.effective_coverages,
            "effective_exclusions": self.effective_exclusions,
            "synthesis_metadata": self.synthesis_metadata,
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
            SectionType.COVERAGE_GRANT: CoveragesExtractor,  # Coverage grants use CoveragesExtractor
            SectionType.COVERAGE_EXTENSION: CoveragesExtractor,  # Coverage extensions use CoveragesExtractor
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
            SectionType.COVERAGE_GRANT: [
                "coverage_grant", "liability coverage", "physical damage coverage",
                "covered autos liability", "section ii", "section iii"
            ],
            SectionType.COVERAGE_EXTENSION: [
                "coverage_extension", "coverage extension", "additional coverages",
                "supplementary payments", "optional coverages"
            ],
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

        # Run synthesis to produce effective coverages/exclusions
        if section_results:
            try:
                synthesis_orchestrator = SynthesisOrchestrator()
                synthesis_result = synthesis_orchestrator.synthesize(result.to_dict())

                # Store synthesis result in the DocumentExtractionResult
                result.effective_coverages = synthesis_result.get("effective_coverages", [])
                result.effective_exclusions = synthesis_result.get("effective_exclusions", [])
                result.synthesis_metadata = {
                    "overall_confidence": synthesis_result.get("overall_confidence", 0.0),
                    "synthesis_method": synthesis_result.get("synthesis_method", "endorsement_only"),
                    "source_endorsement_count": synthesis_result.get("source_endorsement_count", 0),
                }

                # Create synthesized section results for coverages and exclusions
                # This enables coverage-centric output where endorsements
                # are projected into coverage and exclusion sections
                synthesized_sections = self._create_synthesized_section_results(
                    effective_coverages=result.effective_coverages,
                    effective_exclusions=result.effective_exclusions,
                    synthesis_confidence=synthesis_result.get("overall_confidence", 0.0),
                )

                # Add synthesized sections to results
                for synth_section in synthesized_sections:
                    result.section_results.append(synth_section)

                LOGGER.info(
                    "Synthesis completed",
                    extra={
                        "effective_coverages": len(result.effective_coverages),
                        "effective_exclusions": len(result.effective_exclusions),
                        "synthesized_sections": len(synthesized_sections),
                        "confidence": synthesis_result.get("overall_confidence", 0.0),
                    }
                )
            except Exception as e:
                LOGGER.warning(f"Synthesis failed, continuing without: {e}")
                result.effective_coverages = []
                result.effective_exclusions = []
                result.synthesis_metadata = {"error": str(e)}

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

    def _group_chunks_by_endorsement(
        self,
        chunks: List[HybridChunk],
    ) -> List[List[HybridChunk]]:
        """Group chunks that belong to the same multi-page endorsement.

        This ensures that all pages of a single endorsement are processed together,
        maintaining context for accurate extraction.

        Args:
            chunks: List of chunks from endorsement section

        Returns:
            List of chunk groups, each group contains chunks from same endorsement
        """
        if not chunks:
            return []

        # Sort chunks by their primary page number
        sorted_chunks = sorted(chunks, key=lambda c: c.metadata.page_number)

        # Group chunks by contiguous page ranges
        # Chunks with overlapping or adjacent page ranges are grouped together
        groups = []
        current_group = []
        current_max_page = -1

        for chunk in sorted_chunks:
            page_range = chunk.metadata.page_range or [chunk.metadata.page_number]
            min_page = min(page_range)
            max_page = max(page_range)

            # Check if this chunk is contiguous with current group
            # Allow for 1-page gap to handle page boundaries
            if current_group and min_page <= current_max_page + 1:
                # This chunk is contiguous - add to current group
                current_group.append(chunk)
                current_max_page = max(current_max_page, max_page)
            else:
                # New endorsement starts - save current group and start new one
                if current_group:
                    groups.append(current_group)
                current_group = [chunk]
                current_max_page = max_page

        # Don't forget the last group
        if current_group:
            groups.append(current_group)

        LOGGER.debug(
            f"Grouped {len(chunks)} chunks into {len(groups)} endorsement groups",
            extra={
                "group_sizes": [len(g) for g in groups],
                "group_page_ranges": [
                    [min(c.metadata.page_number for c in g), max(c.metadata.page_number for c in g)]
                    for g in groups
                ],
            }
        )

        return groups

    async def _extract_section_batched(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a section in multiple batches.

        For endorsement sections, chunks are first grouped by endorsement to ensure
        multi-page endorsements are processed together for accurate extraction.

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
        is_endorsement_projection = False
        if super_chunk.chunks:
            metadata = super_chunk.chunks[0].metadata
            if (metadata.original_section_type == SectionType.ENDORSEMENTS and
                metadata.effective_section_type == SectionType.COVERAGES and
                metadata.semantic_role == SemanticRole.COVERAGE_MODIFIER):
                extractor_key = "endorsement_coverage_projection"
                is_endorsement_projection = True
            elif (metadata.original_section_type == SectionType.ENDORSEMENTS and
                  metadata.effective_section_type == SectionType.EXCLUSIONS and
                  metadata.semantic_role == SemanticRole.EXCLUSION_MODIFIER):
                extractor_key = "endorsement_exclusion_projection"
                is_endorsement_projection = True

        extractor = self.factory.get_extractor(extractor_key) or self.factory.get_extractor("default")

        # For endorsement projections, group by endorsement first to keep multi-page endorsements together
        if is_endorsement_projection or super_chunk.section_type == SectionType.ENDORSEMENTS:
            endorsement_groups = self._group_chunks_by_endorsement(super_chunk.chunks)

            # Create batches from endorsement groups, keeping each endorsement together
            chunk_batches = []
            current_batch = []
            current_tokens = 0

            for endo_group in endorsement_groups:
                group_tokens = sum(c.metadata.token_count for c in endo_group)

                # If adding this endorsement exceeds threshold, finalize current batch first
                if current_batch and (current_tokens + group_tokens > BATCH_TOKEN_THRESHOLD or
                                    len(current_batch) + len(endo_group) > BATCH_CHUNK_THRESHOLD):
                    chunk_batches.append(current_batch)
                    current_batch = []
                    current_tokens = 0

                # Add entire endorsement group together (never split a single endorsement)
                current_batch.extend(endo_group)
                current_tokens += group_tokens

            if current_batch:
                chunk_batches.append(current_batch)

            LOGGER.info(
                f"Created {len(chunk_batches)} batches from {len(endorsement_groups)} endorsement groups "
                f"for section {super_chunk.section_type.value}"
            )
        else:
            # Standard batching for non-endorsement sections
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
        failed_batches = []
        successful_batches = 0

        for i, batch in enumerate(chunk_batches):
            batch_super_chunk = SectionSuperChunk(
                section_type=super_chunk.section_type,
                section_name=super_chunk.section_name,
                chunks=batch,
                document_id=document_id,
            )

            # Get page range for this batch for logging
            batch_pages = []
            for chunk in batch:
                if chunk.metadata.page_range:
                    batch_pages.extend(chunk.metadata.page_range)
                else:
                    batch_pages.append(chunk.metadata.page_number)
            batch_page_range = f"{min(batch_pages)}-{max(batch_pages)}" if batch_pages else "unknown"

            try:
                LOGGER.debug(
                    f"Processing batch {i+1}/{len(chunk_batches)} for {super_chunk.section_type.value} "
                    f"(pages {batch_page_range}, {batch_super_chunk.total_tokens} tokens)"
                )
                parsed = await self._run_extraction_call(extractor, batch_super_chunk)
                if parsed:
                    parsed_results.append(parsed)
                    successful_batches += 1

                    # Log extraction summary for this batch
                    if is_endorsement_projection:
                        mods_count = len(parsed.get("modifications", []))
                        endo_num = parsed.get("endorsement_number", "unknown")
                        LOGGER.debug(
                            f"Batch {i+1} extracted {mods_count} modifications from endorsement {endo_num}"
                        )
                else:
                    LOGGER.warning(
                        f"Batch {i+1} returned empty result for {super_chunk.section_type.value}"
                    )
                    failed_batches.append({"batch": i+1, "pages": batch_page_range, "reason": "empty_result"})

                total_input_tokens += batch_super_chunk.total_tokens

            except Exception as e:
                LOGGER.error(
                    f"Batch {i+1} failed for {super_chunk.section_type.value} (pages {batch_page_range}): {e}",
                    exc_info=True
                )
                failed_batches.append({"batch": i+1, "pages": batch_page_range, "reason": str(e)})

        # Log summary
        if failed_batches:
            LOGGER.warning(
                f"Section {super_chunk.section_type.value}: {successful_batches}/{len(chunk_batches)} batches succeeded, "
                f"{len(failed_batches)} failed",
                extra={"failed_batches": failed_batches}
            )
        
        if not parsed_results:
            return SectionExtractionResult(section_type=super_chunk.section_type)

        # Aggregate results - pass is_endorsement_projection flag for proper handling
        aggregated_parsed = self._aggregate_batch_results(
            parsed_results,
            super_chunk.section_type,
            is_endorsement_projection=is_endorsement_projection
        )
        
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
        is_endorsement_projection: bool = False,
    ) -> Dict[str, Any]:
        """Aggregate results from multiple extraction batches.

        Handles both regular section extraction and endorsement projection results.
        For endorsement projections, each batch may contain results from different
        endorsements that should be preserved separately.

        Args:
            parsed_results: List of parsed JSON records from LLM calls
            section_type: The section type
            is_endorsement_projection: Whether this is an endorsement projection extraction

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

        # Handle endorsement projection results differently
        # These return per-endorsement results with "modifications" key
        if is_endorsement_projection:
            return self._aggregate_endorsement_projection_results(parsed_results)

        # List items to aggregate for specific section types
        # Coverage-related sections (COVERAGE_GRANT, COVERAGE_EXTENSION) also extract coverages
        list_keys = {
            SectionType.COVERAGES: "coverages",
            SectionType.COVERAGE_GRANT: "coverages",  # Coverage grants extract to coverages
            SectionType.COVERAGE_EXTENSION: "coverages",  # Coverage extensions extract to coverages
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
        extraction_counts = []  # Track number of items per batch for weighted confidence

        for res in parsed_results:
            # Aggregate entities
            if "entities" in res and isinstance(res["entities"], list):
                aggregated["entities"].extend(res["entities"])

            # Aggregate specific lists
            if target_list_key and target_list_key in res and isinstance(res[target_list_key], list):
                items = res[target_list_key]
                aggregated[target_list_key].extend(items)
                extraction_counts.append(len(items))
            elif not target_list_key:
                # For non-list sections, we might have nested fields or keys
                # e.g. Declarations. We merge top-level keys if they don't exist.
                for k, v in res.items():
                    if k not in ["entities", "confidence"]:
                        if k not in aggregated:
                            aggregated[k] = v
                        elif isinstance(aggregated[k], list) and isinstance(v, list):
                            aggregated[k].extend(v)
                        elif isinstance(aggregated[k], dict) and isinstance(v, dict):
                            aggregated[k].update(v)
                extraction_counts.append(1)

            # Collect confidence
            if "confidence" in res:
                try:
                    confidences.append(float(res["confidence"]))
                except (ValueError, TypeError):
                    pass

        # Weighted average confidence by number of extractions
        if confidences and extraction_counts and len(confidences) == len(extraction_counts):
            total_extractions = sum(extraction_counts)
            if total_extractions > 0:
                weighted_conf = sum(c * n for c, n in zip(confidences, extraction_counts))
                aggregated["confidence"] = weighted_conf / total_extractions
            else:
                aggregated["confidence"] = sum(confidences) / len(confidences)
        elif confidences:
            aggregated["confidence"] = sum(confidences) / len(confidences)

        # Deduplicate entities
        aggregated["entities"] = self._deduplicate_entities(aggregated["entities"])

        return aggregated

    def _aggregate_endorsement_projection_results(
        self,
        parsed_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate endorsement projection results from multiple batches.

        Each batch may contain results from one or more endorsements. This method
        preserves per-endorsement identity while aggregating all modifications.

        The projection prompts return:
        {
            "endorsement_number": "...",
            "endorsement_name": "...",
            "modifications": [...],
            "entities": [...],
            "confidence": 0.0
        }

        We aggregate into:
        {
            "endorsements": [
                {"endorsement_number": "...", "endorsement_name": "...", "modifications": [...]}
            ],
            "all_modifications": [...],  # Flattened for easy access
            "entities": [...],
            "confidence": 0.0
        }

        Args:
            parsed_results: List of parsed JSON records from endorsement projection calls

        Returns:
            Aggregated dictionary with preserved endorsement identity
        """
        aggregated = {
            "endorsements": [],
            "all_modifications": [],
            "entities": [],
            "confidence": 0.0,
        }

        confidences = []
        modification_counts = []

        for res in parsed_results:
            # Extract endorsement-level info
            endorsement_number = res.get("endorsement_number")
            endorsement_name = res.get("endorsement_name")
            form_edition_date = res.get("form_edition_date")
            modifications = res.get("modifications", [])

            # Create endorsement record with its modifications
            if endorsement_number or modifications:
                endorsement_record = {
                    "endorsement_number": endorsement_number,
                    "endorsement_name": endorsement_name,
                    "form_edition_date": form_edition_date,
                    "modifications": modifications,
                }
                aggregated["endorsements"].append(endorsement_record)

                # Also add to flattened list with endorsement reference
                for mod in modifications:
                    mod_with_ref = {**mod, "source_endorsement": endorsement_number}
                    aggregated["all_modifications"].append(mod_with_ref)

                modification_counts.append(len(modifications))

            # Aggregate entities
            if "entities" in res and isinstance(res["entities"], list):
                aggregated["entities"].extend(res["entities"])

            # Collect confidence
            if "confidence" in res:
                try:
                    confidences.append(float(res["confidence"]))
                except (ValueError, TypeError):
                    pass

        # Weighted average confidence by number of modifications
        if confidences and modification_counts and len(confidences) == len(modification_counts):
            total_mods = sum(modification_counts)
            if total_mods > 0:
                weighted_conf = sum(c * n for c, n in zip(confidences, modification_counts))
                aggregated["confidence"] = weighted_conf / total_mods
            else:
                aggregated["confidence"] = sum(confidences) / len(confidences) if confidences else 0.0
        elif confidences:
            aggregated["confidence"] = sum(confidences) / len(confidences)

        # Deduplicate entities by ID to prevent duplicates across batches
        aggregated["entities"] = self._deduplicate_entities(aggregated["entities"])

        LOGGER.debug(
            f"Aggregated {len(parsed_results)} endorsement projection batches: "
            f"{len(aggregated['endorsements'])} endorsements, "
            f"{len(aggregated['all_modifications'])} total modifications, "
            f"{len(aggregated['entities'])} unique entities"
        )

        return aggregated

    def _deduplicate_entities(
        self,
        entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Deduplicate entities by ID, keeping the one with highest confidence.

        Args:
            entities: List of entity dictionaries

        Returns:
            Deduplicated list of entities
        """
        if not entities:
            return []

        # Group by entity ID
        entity_map: Dict[str, Dict[str, Any]] = {}

        for entity in entities:
            entity_id = entity.get("id")
            if not entity_id:
                # No ID - keep as is (add to list without dedup)
                entity_id = f"_no_id_{len(entity_map)}"

            existing = entity_map.get(entity_id)
            if existing:
                # Keep the one with higher confidence
                existing_conf = existing.get("confidence", 0.0)
                new_conf = entity.get("confidence", 0.0)
                if new_conf > existing_conf:
                    entity_map[entity_id] = entity
            else:
                entity_map[entity_id] = entity

        return list(entity_map.values())

    def _create_synthesized_section_results(
        self,
        effective_coverages: List[Dict[str, Any]],
        effective_exclusions: List[Dict[str, Any]],
        synthesis_confidence: float,
    ) -> List[SectionExtractionResult]:
        """Create synthesized section results from effective coverages and exclusions.

        This method transforms endorsement-centric extraction into coverage-centric
        and exclusion-centric section results, following the approach
        where endorsements are projected into coverage and exclusion sections.

        Args:
            effective_coverages: List of synthesized coverage objects
            effective_exclusions: List of synthesized exclusion objects
            synthesis_confidence: Overall confidence from synthesis

        Returns:
            List of SectionExtractionResult for coverages and exclusions
        """
        synthesized_sections = []

        # Create coverages section if we have effective coverages
        if effective_coverages:
            # Extract entities from coverages for entity aggregation
            coverage_entities = []
            for cov in effective_coverages:
                entity_id = f"coverage_{cov.get('coverage_name', 'unknown').replace(' ', '_').lower()}"
                coverage_entities.append({
                    "id": entity_id,
                    "type": "Coverage",
                    "attributes": {
                        "name": cov.get("coverage_name"),
                        "coverage_type": cov.get("coverage_type"),
                    },
                    "confidence": cov.get("confidence", synthesis_confidence),
                })

            coverages_result = SectionExtractionResult(
                section_type=SectionType.COVERAGES,
                extracted_data={"coverages": effective_coverages},
                entities=coverage_entities,
                confidence=synthesis_confidence,
                token_count=0,  # Synthesized, not directly extracted
                processing_time_ms=0,
            )
            synthesized_sections.append(coverages_result)

            LOGGER.debug(
                f"Created synthesized coverages section with {len(effective_coverages)} coverages"
            )

        # Create exclusions section if we have effective exclusions
        if effective_exclusions:
            # Extract entities from exclusions for entity aggregation
            exclusion_entities = []
            for excl in effective_exclusions:
                entity_id = f"exclusion_{excl.get('exclusion_name', 'unknown').replace(' ', '_').lower()}"
                exclusion_entities.append({
                    "id": entity_id,
                    "type": "Exclusion",
                    "attributes": {
                        "name": excl.get("exclusion_name"),
                        "effective_state": excl.get("effective_state"),
                        "severity": excl.get("severity"),
                    },
                    "confidence": excl.get("confidence", synthesis_confidence),
                })

            exclusions_result = SectionExtractionResult(
                section_type=SectionType.EXCLUSIONS,
                extracted_data={"exclusions": effective_exclusions},
                entities=exclusion_entities,
                confidence=synthesis_confidence,
                token_count=0,  # Synthesized, not directly extracted
                processing_time_ms=0,
            )
            synthesized_sections.append(exclusions_result)

            LOGGER.debug(
                f"Created synthesized exclusions section with {len(effective_exclusions)} exclusions"
            )

        return synthesized_sections

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

