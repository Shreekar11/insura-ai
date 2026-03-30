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
from app.services.extracted.services.extraction.section.endorsement_provision_extractor import (
    EndorsementProvisionExtractor,
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionExtractionResult":
        """Reconstruct from dictionary."""
        return cls(
            section_type=SectionType(data["section_type"]),
            extracted_data=data["extracted_data"],
            entities=data["entities"],
            confidence=data["confidence"],
            token_count=data["token_count"],
            processing_time_ms=data["processing_time_ms"],
            extraction_id=UUID(data["extraction_id"]) if data.get("extraction_id") else None,
        )


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentExtractionResult":
        """Reconstruct from dictionary."""
        return cls(
            document_id=UUID(data["document_id"]) if data.get("document_id") else None,
            section_results=[SectionExtractionResult.from_dict(sr) for sr in data["section_results"]],
            all_entities=data["all_entities"],
            total_tokens=data["total_tokens"],
            total_processing_time_ms=data["total_processing_time_ms"],
            effective_coverages=data["effective_coverages"],
            effective_exclusions=data["effective_exclusions"],
            synthesis_metadata=data["synthesis_metadata"],
        )


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
        self.factory.register_extractor(
            section_types=["endorsement_provision"],
            extractor_class=EndorsementProvisionExtractor
        )
        
        LOGGER.debug(
            f"Registered {len(extractor_registry)} section extractors with factory"
        )

    @staticmethod
    def get_idempotency_key(workflow_id: UUID, document_id: UUID, section_type: str) -> str:
        """Generate deterministic idempotency key for extraction."""
        return f"{workflow_id}:{document_id}:{section_type}"
    
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

                # Citation creation is deferred to the indexing stage (after chunk
                # embeddings are generated) so Tier 2 semantic search has data.
            except Exception as e:
                LOGGER.warning(f"Synthesis failed, continuing without: {e}")
                result.effective_coverages = []
                result.effective_exclusions = []
                result.synthesis_metadata = {"error": str(e)}

        # Persist extraction results (OLD WAY - for backward compatibility)
        if workflow_id and document_id:
            await self.persist_document_extraction_result(result, workflow_id)

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

    async def extract_section_compute(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Perform LLM extraction for a section WITHOUT persisting.
        
        Args:
            super_chunk: Section super-chunk
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult
        """
        # Determine if batching is needed
        if (super_chunk.total_tokens > BATCH_TOKEN_THRESHOLD or 
            len(super_chunk.chunks) > BATCH_CHUNK_THRESHOLD):
            return await self._extract_section_batched_compute(super_chunk, document_id, workflow_id)
        
        return await self._extract_section_single_compute(super_chunk, document_id, workflow_id)

    async def persist_document_extraction_result(
        self,
        result: DocumentExtractionResult,
        workflow_id: UUID,
    ):
        """Persist all results in a DocumentExtractionResult.
        
        Args:
            result: Complete result
            workflow_id: Workflow ID
        """
        # 1. Persist each section extraction
        for section_res in result.section_results:
            if not section_res.extracted_data and section_res.confidence == 0.0:
                 continue
            
            # Re-generate source_chunks if not present (needed if persisting from external data)
            # This is a bit tricky since SectionExtractionResult doesn't store full source chunks
            # but usually it's called right after extraction where we have them.
            
            # If extraction_id is already set, it means it was already persisted
            # but we might still need to persist step outputs
            pass

        # 2. Persist step outputs
        await self._persist_step_outputs(result, workflow_id)
        await self.session.commit()

    async def persist_section_extraction(
        self,
        section_result: SectionExtractionResult,
        document_id: UUID,
        workflow_id: UUID,
        source_chunks: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """Persist a single section extraction result.
        
        Args:
            section_result: Result to persist
            document_id: Document ID
            workflow_id: Workflow ID
            source_chunks: Source chunk metadata
            
        Returns:
            UUID of created extraction record
        """
        idempotency_key = self.get_idempotency_key(workflow_id, document_id, section_result.section_type.value)
        
        # Build page_range dict
        page_range_dict = None
        # Try to infer from section_result if we can, but usually we pass it in
        
        # Include entities in extracted_fields
        extracted_fields_with_entities = {
            **section_result.extracted_data,
            "entities": section_result.entities
        }
        
        confidence_dict = {"overall": section_result.confidence}

        extraction = await self.section_extraction_repo.create_section_extraction(
            document_id=document_id,
            workflow_id=workflow_id,
            section_type=section_result.section_type.value,
            extracted_fields=extracted_fields_with_entities,
            page_range=None, # Filled by repo or passed in
            confidence=confidence_dict,
            source_chunks=source_chunks,
            model_version=self.model,
            prompt_version="v1_split",
        )
        
        # Set idempotency key explicitly
        extraction.idempotency_key = idempotency_key
        await self.session.flush()
        
        return extraction.id
    
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
        """Extract data and PERSIST (legacy path)."""
        result = await self._extract_section_single_compute(super_chunk, document_id, workflow_id)
        
        if document_id and workflow_id:
            # Re-build source_chunks
            all_stable_ids = [c.metadata.stable_chunk_id for c in super_chunk.chunks if c.metadata.stable_chunk_id]
            source_chunks = {
                "chunk_ids": [],
                "stable_chunk_ids": all_stable_ids,
                "page_range": super_chunk.page_range,
            }
            extraction_id = await self.persist_section_extraction(
                result, document_id, workflow_id, source_chunks
            )
            result.extraction_id = extraction_id
            
        return result

    async def _extract_section_batched(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data (batched) and PERSIST (legacy path)."""
        result = await self._extract_section_batched_compute(super_chunk, document_id, workflow_id)
        
        if document_id and workflow_id:
            all_stable_ids = [c.metadata.stable_chunk_id for c in super_chunk.chunks if c.metadata.stable_chunk_id]
            source_chunks = {
                "chunk_ids": [],
                "stable_chunk_ids": all_stable_ids,
                "page_range": super_chunk.page_range,
            }
            extraction_id = await self.persist_section_extraction(
                result, document_id, workflow_id, source_chunks
            )
            result.extraction_id = extraction_id
            
        return result

    async def _extract_section_single_compute(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a single section super-chunk WITHOUT persisting.
        
        Args:
            super_chunk: Section super-chunk to extract
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult
        """
        start_time = time.time()
        
        # Determine if we should use a projection extractor based on semantic role
        extractor_key = super_chunk.section_type.value

        if super_chunk.chunks:
            metadata = super_chunk.chunks[0].metadata

            # Normalize semantic role
            semantic_role_str = (
                metadata.semantic_role.value
                if hasattr(metadata.semantic_role, 'value')
                else str(metadata.semantic_role) if metadata.semantic_role else None
            )

            is_endorsement_source = (
                metadata.original_section_type == SectionType.ENDORSEMENTS or
                metadata.section_type == SectionType.ENDORSEMENTS
            )

            is_coverage_modifier = (
                semantic_role_str in (SemanticRole.COVERAGE_MODIFIER.value, "coverage_modifier") or
                (metadata.coverage_effects and any(e for e in metadata.coverage_effects))
            )

            is_exclusion_modifier = (
                semantic_role_str in (SemanticRole.EXCLUSION_MODIFIER.value, "exclusion_modifier") or
                (metadata.exclusion_effects and any(e for e in metadata.exclusion_effects))
            )

            is_both_modifier = semantic_role_str in (SemanticRole.BOTH.value, "both")

            if is_endorsement_source:
                if is_both_modifier:
                    extractor_key = "endorsement_provision"
                elif is_coverage_modifier:
                    extractor_key = "endorsement_coverage_projection"
                elif is_exclusion_modifier:
                    extractor_key = "endorsement_exclusion_projection"
        
        # Get section-specific extractor from factory
        extractor = self.factory.get_extractor(extractor_key) or self.factory.get_extractor("default")
        
        try:
            # Use helper to run extraction call
            parsed = await self._run_extraction_call(extractor, super_chunk)
            
            if parsed is None:
                parsed = {}
            
            # Extract fields
            if hasattr(extractor, 'extract_fields'):
                extracted_data = extractor.extract_fields(parsed)
            else:
                extracted_data = self._extract_section_data(parsed, super_chunk.section_type)

            # Inject page_numbers
            if super_chunk.page_range:
                extracted_data = self._inject_page_numbers(
                    extracted_data,
                    super_chunk.page_range,
                    super_chunk.section_type.value
                )

            # Tag projection type
            if extractor_key == "endorsement_coverage_projection":
                extracted_data["_projection_type"] = "coverage"
            elif extractor_key == "endorsement_exclusion_projection":
                extracted_data["_projection_type"] = "exclusion"

            entities = parsed.get("entities", [])
            confidence = float(parsed.get("confidence", 0.0))
            processing_time = int((time.time() - start_time) * 1000)
            
            return SectionExtractionResult(
                section_type=super_chunk.section_type,
                extracted_data=extracted_data,
                entities=entities,
                confidence=confidence,
                token_count=super_chunk.total_tokens,
                processing_time_ms=processing_time,
                extraction_id=None,
            )
            
        except Exception as e:
            LOGGER.error(f"Section extraction compute failed: {e}", exc_info=True)
            raise

    def _inject_page_numbers(
        self,
        extracted_data: Dict[str, Any],
        page_range: List[int],
        section_type: str,
    ) -> Dict[str, Any]:
        """Inject page_numbers into extracted items for citation support.

        This method adds page_numbers to each extracted coverage, exclusion,
        or other item so that citations can map back to source PDF locations.

        Args:
            extracted_data: Dict of extracted fields from LLM
            page_range: List of page numbers from the source chunk
            section_type: Type of section (COVERAGES, EXCLUSIONS, etc.)

        Returns:
            extracted_data with page_numbers injected into items
        """
        if not page_range:
            LOGGER.warning(
                f"[PAGE-INJECT] No page_range provided for {section_type}, skipping injection"
            )
            return extracted_data

        # Fields that contain lists of items to inject page_numbers into
        item_fields = [
            "coverages",
            "exclusions",
            "conditions",
            "endorsements",
            "definitions",
            "modifications",
        ]

        injection_stats = {}

        for field in item_fields:
            items = extracted_data.get(field, [])
            if isinstance(items, list) and items:
                injected_count = 0
                for item in items:
                    if isinstance(item, dict):
                        # Only inject if not already present
                        if "page_numbers" not in item or not item.get("page_numbers"):
                            item["page_numbers"] = list(page_range)
                            injected_count += 1
                        
                        # Endorsements have nested modifications lists that also need page numbers
                        if field == "endorsements" and "modifications" in item:
                            nested_mods = item["modifications"]
                            if isinstance(nested_mods, list):
                                for mod in nested_mods:
                                    if isinstance(mod, dict) and ("page_numbers" not in mod or not mod.get("page_numbers")):
                                        mod["page_numbers"] = list(page_range)
                                        if "source_text" not in mod and "verbatim_language" in mod:
                                            mod["source_text"] = mod["verbatim_language"]

                        # Also inject source_text if description is available
                        if "source_text" not in item and "description" in item:
                            item["source_text"] = item["description"]

                if injected_count > 0:
                    injection_stats[field] = {
                        "total_items": len(items),
                        "injected": injected_count,
                    }

        LOGGER.info(
            f"[PAGE-INJECT] Injected page_numbers into {section_type} extracted data",
            extra={
                "section_type": section_type,
                "page_range": page_range,
                "injection_stats": injection_stats,
                "fields_with_items": [f for f in item_fields if extracted_data.get(f)],
            }
        )

        # Log sample item for verification
        for field in item_fields:
            items = extracted_data.get(field, [])
            if isinstance(items, list) and items and isinstance(items[0], dict):
                sample = items[0]
                LOGGER.debug(
                    f"[PAGE-INJECT] Sample {field} item after injection",
                    extra={
                        "field": field,
                        "has_page_numbers": "page_numbers" in sample,
                        "page_numbers": sample.get("page_numbers"),
                        "has_source_text": "source_text" in sample,
                        "item_keys": list(sample.keys()),
                    }
                )
                break

        return extracted_data

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

    async def _extract_section_batched_compute(
        self,
        super_chunk: SectionSuperChunk,
        document_id: UUID,
        workflow_id: UUID,
    ) -> SectionExtractionResult:
        """Extract data from a section in multiple batches WITHOUT persisting.
        
        Args:
            super_chunk: Large section super-chunk
            document_id: Document ID
            workflow_id: Workflow ID
            
        Returns:
            SectionExtractionResult (aggregated)
        """
        start_time = time.time()

        # Determine extractor to use
        extractor_key = super_chunk.section_type.value
        is_endorsement_projection = False
        if super_chunk.chunks:
            metadata = super_chunk.chunks[0].metadata
            semantic_role_str = (
                metadata.semantic_role.value
                if hasattr(metadata.semantic_role, 'value')
                else str(metadata.semantic_role) if metadata.semantic_role else None
            )
            is_endorsement_source = (
                metadata.original_section_type == SectionType.ENDORSEMENTS or
                metadata.section_type == SectionType.ENDORSEMENTS
            )
            is_coverage_modifier = (
                semantic_role_str in (SemanticRole.COVERAGE_MODIFIER.value, "coverage_modifier") or
                (metadata.coverage_effects and any(e for e in metadata.coverage_effects))
            )
            is_exclusion_modifier = (
                semantic_role_str in (SemanticRole.EXCLUSION_MODIFIER.value, "exclusion_modifier") or
                (metadata.exclusion_effects and any(e for e in metadata.exclusion_effects))
            )
            is_both_modifier = semantic_role_str in (SemanticRole.BOTH.value, "both")

            if is_endorsement_source:
                if is_both_modifier:
                    if metadata.effective_section_type == SectionType.EXCLUSIONS:
                        extractor_key = "endorsement_exclusion_projection"
                    else:
                        extractor_key = "endorsement_coverage_projection"
                    is_endorsement_projection = True
                elif is_coverage_modifier and metadata.effective_section_type == SectionType.COVERAGES:
                    extractor_key = "endorsement_coverage_projection"
                    is_endorsement_projection = True
                elif is_exclusion_modifier and metadata.effective_section_type == SectionType.EXCLUSIONS:
                    extractor_key = "endorsement_exclusion_projection"
                    is_endorsement_projection = True

        extractor = self.factory.get_extractor(extractor_key) or self.factory.get_extractor("default")

        # Grouping logic
        if is_endorsement_projection or super_chunk.section_type == SectionType.ENDORSEMENTS:
            endorsement_groups = self._group_chunks_by_endorsement(super_chunk.chunks)
            chunk_batches = []
            current_batch = []
            current_tokens = 0
            for endo_group in endorsement_groups:
                group_tokens = sum(c.metadata.token_count for c in endo_group)
                if current_batch and (current_tokens + group_tokens > BATCH_TOKEN_THRESHOLD or
                                    len(current_batch) + len(endo_group) > BATCH_CHUNK_THRESHOLD):
                    chunk_batches.append(current_batch)
                    current_batch = []
                    current_tokens = 0
                current_batch.extend(endo_group)
                current_tokens += group_tokens
            if current_batch:
                chunk_batches.append(current_batch)
        else:
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
                parsed = await self._run_extraction_call(extractor, batch_super_chunk)
                if parsed:
                    parsed_results.append(parsed)
                total_input_tokens += batch_super_chunk.total_tokens
            except Exception as e:
                LOGGER.error(f"Batch {i+1} failed: {e}")

        if not parsed_results:
            return SectionExtractionResult(section_type=super_chunk.section_type)

        aggregated_parsed = self._aggregate_batch_results(
            parsed_results,
            super_chunk.section_type,
            is_endorsement_projection=is_endorsement_projection
        )
        
        if hasattr(extractor, 'extract_fields'):
            extracted_data = extractor.extract_fields(aggregated_parsed)
        else:
            extracted_data = self._extract_section_data(aggregated_parsed, super_chunk.section_type)

        if super_chunk.page_range:
            extracted_data = self._inject_page_numbers(
                extracted_data,
                super_chunk.page_range,
                super_chunk.section_type.value
            )

        if extractor_key == "endorsement_coverage_projection":
            extracted_data["_projection_type"] = "coverage"
        elif extractor_key == "endorsement_exclusion_projection":
            extracted_data["_projection_type"] = "exclusion"

        entities = aggregated_parsed.get("entities", [])
        confidence = float(aggregated_parsed.get("confidence", 0.0))
        processing_time = int((time.time() - start_time) * 1000)
        
        return SectionExtractionResult(
            section_type=super_chunk.section_type,
            extracted_data=extracted_data,
            entities=entities,
            confidence=confidence,
            token_count=total_input_tokens,
            processing_time_ms=processing_time,
            extraction_id=None,
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

