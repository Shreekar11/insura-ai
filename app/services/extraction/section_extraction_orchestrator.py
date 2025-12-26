"""Section extraction orchestrator for Tier 2 LLM processing.

This service implements the v2 architecture's Tier 2 processing:
- Sequential section-level extraction
- Section-specific field extraction
- Batch processing of section super-chunks
- Structured JSON output per section type

Processes sections in priority order with section-specific prompts.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unified_llm import UnifiedLLMClient, create_llm_client_from_settings
from app.services.chunking.hybrid_models import (
    SectionType,
    SectionSuperChunk,
    HybridChunk,
)
from app.services.chunking.section_super_chunk_builder import SuperChunkBatch
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "section_type": self.section_type.value,
            "extracted_data": self.extracted_data,
            "entities": self.entities,
            "confidence": self.confidence,
            "token_count": self.token_count,
            "processing_time_ms": self.processing_time_ms,
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


# Section-specific extraction prompts
SECTION_PROMPTS = {
    SectionType.DECLARATIONS: """You are an expert at extracting structured data from insurance policy declarations pages.

Extract the following fields from the declarations section:

## Required Fields:
- policy_number: Policy number/ID
- insured_name: Named insured (primary)
- insured_address: Insured's address
- effective_date: Policy effective date (YYYY-MM-DD)
- expiration_date: Policy expiration date (YYYY-MM-DD)
- carrier_name: Insurance carrier/company name
- broker_name: Broker/agent name (if present)
- total_premium: Total policy premium
- policy_type: Type of policy (e.g., Commercial Property, General Liability)

## Optional Fields:
- additional_insureds: List of additional insureds
- policy_form: Policy form number
- retroactive_date: Retroactive date if applicable
- prior_acts_coverage: Prior acts coverage details

## Entities to Extract:
- POLICY_NUMBER
- INSURED_NAME
- CARRIER
- BROKER
- AMOUNT (premiums, limits)
- DATE
- ADDRESS

Return JSON with this structure:
{
    "fields": {
        "policy_number": "...",
        "insured_name": "...",
        ...
    },
    "entities": [
        {"type": "POLICY_NUMBER", "value": "...", "confidence": 0.95},
        ...
    ],
    "confidence": 0.92
}
""",

    SectionType.COVERAGES: """You are an expert at extracting coverage information from insurance policies.

Extract ALL coverage items with the following details:

## Per Coverage:
- coverage_name: Name of the coverage
- coverage_type: Type (Property, Liability, Auto, Workers Comp, etc.)
- limit_amount: Coverage limit (numeric)
- deductible_amount: Deductible (numeric)
- premium_amount: Premium for this coverage (if shown)
- description: What is covered
- sub_limits: Any sub-limits (as object)
- per_occurrence: Is limit per occurrence? (boolean)
- aggregate: Is there an aggregate limit? (boolean)
- aggregate_amount: Aggregate limit amount if applicable
- coverage_territory: Geographic coverage territory
- retroactive_date: Retroactive date if applicable

## Entities to Extract:
- COVERAGE_TYPE
- AMOUNT (limits, deductibles, premiums)
- PERCENTAGE (coinsurance, etc.)

Return JSON:
{
    "coverages": [
        {
            "coverage_name": "Building Coverage",
            "coverage_type": "Property",
            "limit_amount": 5000000,
            "deductible_amount": 5000,
            ...
        }
    ],
    "entities": [...],
    "confidence": 0.90
}
""",

    SectionType.CONDITIONS: """You are an expert at extracting policy conditions from insurance documents.

Extract ALL conditions with:

## Per Condition:
- condition_type: Type (Coverage Condition, Claim Condition, General Condition, etc.)
- title: Brief title/name
- description: Full description of the condition
- applies_to: What coverage/section it applies to
- requirements: List of requirements
- consequences: What happens if not met
- reference: Section/clause reference

Return JSON:
{
    "conditions": [
        {
            "condition_type": "Claim Condition",
            "title": "Duties in Event of Loss",
            "description": "...",
            ...
        }
    ],
    "entities": [...],
    "confidence": 0.88
}
""",

    SectionType.EXCLUSIONS: """You are an expert at extracting exclusions from insurance policies.

Extract ALL exclusions with:

## Per Exclusion:
- exclusion_type: Type (General Exclusion, Coverage-Specific, etc.)
- title: Brief title
- description: Full description
- applies_to: What it applies to
- exceptions: List of exceptions to the exclusion
- reference: Section/clause reference

Return JSON:
{
    "exclusions": [
        {
            "exclusion_type": "General Exclusion",
            "title": "War and Military Action",
            "description": "...",
            ...
        }
    ],
    "entities": [...],
    "confidence": 0.87
}
""",

    SectionType.ENDORSEMENTS: """You are an expert at extracting endorsement information from insurance policies.

Extract ALL endorsements with:

## Per Endorsement:
- endorsement_number: Endorsement number/ID
- endorsement_name: Name/title
- effective_date: Effective date
- description: What the endorsement modifies
- premium_change: Premium impact (if any)
- coverage_modified: Which coverage is modified
- adds_coverage: Does it add coverage?
- removes_coverage: Does it remove coverage?
- modifies_limit: Does it modify limits?
- new_limit: New limit if modified

Return JSON:
{
    "endorsements": [
        {
            "endorsement_number": "IL 00 21",
            "endorsement_name": "Additional Insured",
            ...
        }
    ],
    "entities": [...],
    "confidence": 0.85
}
""",

    SectionType.INSURING_AGREEMENT: """You are an expert at extracting insuring agreement details.

Extract:
- agreement_text: Full text of insuring agreement
- covered_causes: Causes of loss covered
- coverage_trigger: What triggers coverage
- key_definitions: Important defined terms
- coverage_basis: Claims-made vs occurrence

Return JSON:
{
    "insuring_agreement": {
        "agreement_text": "...",
        "covered_causes": [...],
        ...
    },
    "entities": [...],
    "confidence": 0.90
}
""",

    SectionType.PREMIUM_SUMMARY: """You are an expert at extracting premium information.

Extract:
- total_premium: Total policy premium
- premium_breakdown: Breakdown by coverage
- taxes_and_fees: Taxes and fees
- payment_terms: Payment terms
- installment_schedule: Installment details if applicable

Return JSON:
{
    "premium": {
        "total_premium": 50000,
        "breakdown": [
            {"coverage": "Property", "premium": 25000},
            ...
        ],
        ...
    },
    "entities": [...],
    "confidence": 0.92
}
""",
}

# Default prompt for unknown sections
DEFAULT_SECTION_PROMPT = """You are an expert at extracting structured information from insurance documents.

Extract all relevant information from this section including:
- Key facts and figures
- Named entities (people, companies, amounts, dates)
- Important terms and conditions

Return JSON:
{
    "extracted_data": {
        // All extracted key-value pairs
    },
    "entities": [
        {"type": "...", "value": "...", "confidence": 0.8}
    ],
    "confidence": 0.75
}
"""


class SectionExtractionOrchestrator:
    """Tier 2 orchestrator for section-level extraction.
    
    This service processes section super-chunks sequentially, applying
    section-specific prompts to extract structured data.
    
    Attributes:
        client: UnifiedLLMClient for LLM API calls
        session: SQLAlchemy session for persistence
    """
    
    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "openai/gpt-oss-20b:free",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        # ollama_model: str = "deepseek-r1:7b",
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
            ollama_model: Ollama model name
            timeout: API timeout
            max_retries: Max retry attempts
        """
        self.session = session
        self.provider = provider
        
        # Initialize LLM client using factory function
        self.client = create_llm_client_from_settings(
            provider=provider,
            gemini_api_key=gemini_api_key or "",
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key or "",
            openrouter_api_url=openrouter_api_url,
            openrouter_model=openrouter_model,
            ollama_api_url="http://localhost:11434",
            ollama_model="deepseek-r1:7b",
            timeout=timeout,
            max_retries=max_retries,
            enable_fallback=False,
        )
        
        self.model = self.client.model
        
        LOGGER.info(
            "Initialized SectionExtractionOrchestrator (Tier 2)",
            extra={"provider": provider, "model": self.model}
        )
    
    async def run(
        self,
        super_chunks: List[SectionSuperChunk],
        document_id: Optional[UUID] = None,
    ) -> DocumentExtractionResult:
        """Run section extraction (BaseService compatibility).
        
        Args:
            super_chunks: List of section super-chunks
            document_id: Document ID
            
        Returns:
            DocumentExtractionResult
        """
        return await self.extract_all_sections(super_chunks, document_id)

    async def extract_all_sections(
        self,
        super_chunks: List[SectionSuperChunk],
        document_id: Optional[UUID] = None,
    ) -> DocumentExtractionResult:
        """Extract data from all section super-chunks.
        
        Processes sections sequentially in priority order.
        
        Args:
            super_chunks: List of section super-chunks
            document_id: Document ID
            
        Returns:
            DocumentExtractionResult with all section extractions
        """
        if not super_chunks:
            return DocumentExtractionResult(document_id=document_id)
        
        # Filter to LLM-required sections only
        llm_sections = [sc for sc in super_chunks if sc.requires_llm]
        
        LOGGER.info(
            "Starting Tier 2 section extraction",
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
            "Tier 2 extraction completed",
            extra={
                "document_id": str(document_id) if document_id else None,
                "sections_extracted": len(section_results),
                "total_entities": len(all_entities),
                "total_tokens": total_tokens,
            }
        )
        
        return result
    
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
        """Extract data from a single section super-chunk.
        
        Args:
            super_chunk: Section super-chunk to extract
            document_id: Document ID
            
        Returns:
            SectionExtractionResult
        """
        import time
        start_time = time.time()
        
        # Get section-specific prompt
        prompt = SECTION_PROMPTS.get(
            super_chunk.section_type, 
            DEFAULT_SECTION_PROMPT
        )
        
        # Combine chunk texts
        section_text = super_chunk.get_contextualized_text()
        
        LOGGER.debug(
            f"Extracting section: {super_chunk.section_type.value}",
            extra={
                "document_id": str(document_id) if document_id else None,
                "chunk_count": len(super_chunk.chunks),
                "total_tokens": super_chunk.total_tokens,
            }
        )
        
        try:
            # Call LLM
            response = await self.client.generate_content(
                contents=f"Extract from this {super_chunk.section_type.value} section:\n\n{section_text}",
                system_instruction=prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            parsed = parse_json_safely(response)
            
            if parsed is None:
                LOGGER.warning(f"Failed to parse extraction response for {super_chunk.section_type}")
                parsed = {}
            
            # Extract fields based on section type
            extracted_data = self._extract_section_data(parsed, super_chunk.section_type)
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
            )
            
        except Exception as e:
            LOGGER.error(f"Section extraction failed: {e}", exc_info=True)
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

