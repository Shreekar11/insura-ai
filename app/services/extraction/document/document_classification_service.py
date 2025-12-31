"""Document classification service for Tier 1 LLM processing.

This service implements the v2 architecture's Tier 1 processing:
- Document type classification
- Section boundary detection
- Page-to-section mapping
- Section map generation

Uses only the first 5-10 pages for efficient classification.
"""

import json
from typing import List, Dict, Any, Optional
from uuid import UUID
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unified_llm import UnifiedLLMClient, create_llm_client_from_settings
from app.services.chunking.hybrid_models import SectionType
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


@dataclass
class SectionBoundary:
    """Represents a detected section boundary.
    
    Attributes:
        section_type: Type of section
        start_page: Starting page number
        end_page: Ending page number (inclusive)
        confidence: Confidence score (0-1)
        anchor_text: Text that triggered section detection
    """
    section_type: SectionType
    start_page: int
    end_page: int
    confidence: float = 0.0
    anchor_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "section_type": self.section_type.value,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "confidence": self.confidence,
            "anchor_text": self.anchor_text,
        }


@dataclass
class DocumentClassificationResult:
    """Result of Tier 1 document classification.
    
    Attributes:
        document_id: Document ID
        document_type: Classified document type
        document_subtype: Optional subtype
        confidence: Classification confidence
        section_boundaries: List of detected section boundaries
        page_section_map: Mapping of page numbers to section types
        metadata: Additional classification metadata
    """
    document_type: str
    document_id: Optional[UUID] = None
    document_subtype: Optional[str] = None
    confidence: float = 0.0
    section_boundaries: List[SectionBoundary] = field(default_factory=list)
    page_section_map: Dict[int, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "document_type": self.document_type,
            "document_subtype": self.document_subtype,
            "confidence": self.confidence,
            "section_boundaries": [sb.to_dict() for sb in self.section_boundaries],
            "page_section_map": self.page_section_map,
            "metadata": self.metadata,
        }
    
    def get_sections_for_extraction(self) -> List[SectionType]:
        """Get list of section types that require extraction."""
        return [sb.section_type for sb in self.section_boundaries]
    
    def get_pages_for_section(self, section_type: SectionType) -> List[int]:
        """Get page numbers for a specific section."""
        for boundary in self.section_boundaries:
            if boundary.section_type == section_type:
                return list(range(boundary.start_page, boundary.end_page + 1))
        return []


class DocumentClassificationService:
    """Tier 1 LLM service for document classification and section mapping.
    
    This service analyzes the first N pages of a document to:
    1. Classify the document type (policy, SOV, loss run, etc.)
    2. Detect section boundaries
    3. Create a page-to-section mapping
    
    This enables efficient downstream processing by identifying which
    sections exist and where they are located.
    
    Attributes:
        client: UnifiedLLMClient for LLM API calls
        max_pages_for_classification: Maximum pages to analyze
    """
    
    CLASSIFICATION_PROMPT = """You are an expert insurance document analyst. Analyze the provided document pages and:

1. **Classify the document type** from these categories:
   - policy: Insurance policy document
   - sov: Schedule of Values
   - loss_run: Loss run / claims history report
   - endorsement: Policy endorsement
   - quote: Insurance quote
   - submission: Insurance submission
   - proposal: Insurance proposal
   - invoice: Premium invoice
   - certificate: Certificate of insurance
   - correspondence: General correspondence
   - financial: Financial statement
   - audit: Audit report
   - unknown: Cannot determine

2. **Identify section boundaries** - detect where these sections start and end:
   - declarations: Policy declarations page
   - coverages: Coverage details
   - conditions: Policy conditions
   - exclusions: Exclusions section
   - endorsements: Endorsements section
   - schedule_of_values: SOV / property schedule
   - loss_run: Loss history / claims data
   - insuring_agreement: Insuring agreement
   - premium_summary: Premium breakdown

3. **Map each page to its section** based on content.

## Output Format (JSON only, no markdown):

{
    "document_type": "policy",
    "document_subtype": "commercial_property",
    "confidence": 0.95,
    "section_boundaries": [
        {
            "section_type": "declarations",
            "start_page": 1,
            "end_page": 3,
            "confidence": 0.98,
            "anchor_text": "DECLARATIONS"
        },
        {
            "section_type": "coverages",
            "start_page": 4,
            "end_page": 12,
            "confidence": 0.92,
            "anchor_text": "COVERAGE FORM"
        }
    ],
    "page_section_map": {
        "1": "declarations",
        "2": "declarations",
        "3": "declarations",
        "4": "coverages"
    },
    "metadata": {
        "has_tables": true,
        "estimated_total_sections": 5,
        "carrier_detected": "ABC Insurance Company"
    }
}

## Rules:
1. Be conservative with confidence scores
2. If a section spans multiple pages, include all pages in the range
3. Some pages may belong to multiple sections (use the primary section)
4. If unsure about section type, use the most likely match
5. Return ONLY valid JSON (no code fences or markdown)
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
        ollama_model: str = "qwen3:8b",
        ollama_api_url: str = "http://localhost:11434",
        groq_api_key: Optional[str] = None,
        groq_model: str = "openai/gpt-oss-20b",
        groq_api_url: str = "",
        max_pages_for_classification: int = 10,
        timeout: int = 300,  # Increased timeout for classification (5 minutes)
    ):
        """Initialize document classification service.
        
        Args:
            session: SQLAlchemy async session (optional)
            provider: LLM provider to use
            gemini_api_key: Gemini API key
            gemini_model: Gemini model name
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model name
            openrouter_api_url: OpenRouter API URL
            ollama_model: Ollama model name
            groq_api_key: Groq API key
            groq_model: Groq model name
            groq_api_url: Groq API URL (optional)
            max_pages_for_classification: Max pages to analyze
            timeout: API timeout in seconds
        """
        self.session = session
        self.provider = provider
        self.max_pages_for_classification = max_pages_for_classification
        
        # Initialize LLM client using factory function
        self.client = create_llm_client_from_settings(
            provider=provider,
            gemini_api_key=gemini_api_key or "",
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key or "",
            openrouter_api_url=openrouter_api_url,
            openrouter_model=openrouter_model,
            ollama_api_url=ollama_api_url,
            ollama_model=ollama_model,
            groq_api_key=groq_api_key or "",
            groq_model=groq_model,
            groq_api_url=groq_api_url,
            timeout=timeout,
            max_retries=3,
            enable_fallback=False,
        )
        
        self.model = self.client.model
        
        LOGGER.info(
            "Initialized DocumentClassificationService (Tier 1)",
            extra={
                "provider": provider,
                "model": self.model,
                "max_pages": max_pages_for_classification,
            }
        )
    
    async def run(
        self,
        pages: List[Any],
        document_id: Optional[UUID] = None,
    ) -> DocumentClassificationResult:
        """Run document classification (BaseService compatibility).
        
        Args:
            pages: List of pages (PageData or text)
            document_id: Optional document ID
            
        Returns:
            DocumentClassificationResult
        """
        # Extract text from page objects if necessary
        pages_text = []
        for page in pages:
            if hasattr(page, "get_content"):
                pages_text.append(page.get_content())
            elif hasattr(page, "text"):
                pages_text.append(page.text)
            else:
                pages_text.append(str(page))
        
        return await self.classify_document(pages_text, document_id)

    async def classify_document(
        self,
        pages_text: List[str],
        document_id: Optional[UUID] = None,
    ) -> DocumentClassificationResult:
        """Classify document and detect section boundaries.
        
        This is the main Tier 1 processing method. It analyzes the first
        N pages to classify the document and map sections.
        
        Args:
            pages_text: List of page texts (first N pages)
            document_id: Optional document ID for logging
            
        Returns:
            DocumentClassificationResult with classification and section map
        """
        if not pages_text:
            LOGGER.warning("Empty pages provided for classification")
            return DocumentClassificationResult(
                document_type="unknown",
                document_id=document_id,
                confidence=0.0,
            )
        
        # Limit pages for classification
        pages_to_analyze = pages_text[:self.max_pages_for_classification]
        
        LOGGER.info(
            "Starting Tier 1 document classification",
            extra={
                "document_id": str(document_id) if document_id else None,
                "pages_to_analyze": len(pages_to_analyze),
                "total_pages": len(pages_text),
            }
        )
        
        try:
            # Prepare input
            LOGGER.info("Formatting pages for LLM input...")
            pages_content = self._format_pages_for_llm(pages_to_analyze)
            LOGGER.info(
                f"Pages formatted, content length: {len(pages_content)} chars",
                extra={"content_preview": pages_content[:500]}
            )
            
            # Call LLM
            LOGGER.info(
                "Calling LLM for document classification...",
                extra={
                    "prompt_length": len(self.CLASSIFICATION_PROMPT),
                    "content_length": len(pages_content),
                    "total_input_size": len(self.CLASSIFICATION_PROMPT) + len(pages_content)
                }
            )
            
            import time
            start_time = time.time()
            
            response = await self.client.generate_content(
                contents=f"Analyze these document pages:\n\n{pages_content}",
                system_instruction=self.CLASSIFICATION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            elapsed_time = time.time() - start_time
            LOGGER.info(
                f"LLM response received in {elapsed_time:.2f}s, length: {len(response)} chars",
                extra={"response_preview": response[:500] if response else "EMPTY", "elapsed_seconds": elapsed_time}
            )
            
            # Parse response
            LOGGER.info("Parsing classification response...")
            result = self._parse_classification_response(response, len(pages_text), document_id)
            LOGGER.info(f"Classification response parsed successfully")
            
            LOGGER.info(
                "Tier 1 classification completed",
                extra={
                    "document_id": str(document_id) if document_id else None,
                    "document_type": result.document_type,
                    "confidence": result.confidence,
                    "sections_detected": len(result.section_boundaries),
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                f"Tier 1 classification failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id) if document_id else None}
            )
            return DocumentClassificationResult(
                document_type="unknown",
                document_id=document_id,
                confidence=0.0,
                metadata={"error": str(e)},
            )
    
    def _format_pages_for_llm(self, pages: List[str]) -> str:
        """Format pages for LLM input.
        
        Args:
            pages: List of page texts
            
        Returns:
            Formatted string for LLM
        """
        formatted_pages = []
        for i, page in enumerate(pages, start=1):
            # Truncate very long pages
            page_text = page[:5000] if len(page) > 5000 else page
            formatted_pages.append(f"=== PAGE {i} ===\n{page_text}")
        
        return "\n\n".join(formatted_pages)
    
    def _parse_classification_response(
        self,
        response: str,
        total_pages: int,
        document_id: Optional[UUID] = None,
    ) -> DocumentClassificationResult:
        """Parse LLM classification response.
        
        Args:
            response: Raw LLM response
            total_pages: Total pages in document
            
        Returns:
            Parsed DocumentClassificationResult
        """
        parsed = parse_json_safely(response)
        
        if parsed is None:
            LOGGER.error("Failed to parse classification response as JSON")
            return DocumentClassificationResult(
                document_type="unknown",
                document_id=document_id,
                confidence=0.0,
            )
        
        # Extract document type
        document_type = parsed.get("document_type", "unknown")
        document_subtype = parsed.get("document_subtype")
        confidence = float(parsed.get("confidence", 0.0))
        
        # Parse section boundaries
        section_boundaries = []
        for sb_data in parsed.get("section_boundaries", []):
            try:
                section_type_str = sb_data.get("section_type", "unknown")
                try:
                    section_type = SectionType(section_type_str)
                except ValueError:
                    section_type = SectionType.UNKNOWN
                
                boundary = SectionBoundary(
                    section_type=section_type,
                    start_page=int(sb_data.get("start_page", 1)),
                    end_page=int(sb_data.get("end_page", 1)),
                    confidence=float(sb_data.get("confidence", 0.0)),
                    anchor_text=sb_data.get("anchor_text"),
                )
                section_boundaries.append(boundary)
            except Exception as e:
                LOGGER.warning(f"Failed to parse section boundary: {e}")
        
        # Parse page section map
        page_section_map = {}
        for page_str, section in parsed.get("page_section_map", {}).items():
            try:
                page_num = int(page_str)
                page_section_map[page_num] = section
            except ValueError:
                pass
        
        # Get metadata
        metadata = parsed.get("metadata", {})
        metadata["total_pages"] = total_pages
        metadata["pages_analyzed"] = min(self.max_pages_for_classification, total_pages)
        
        return DocumentClassificationResult(
            document_type=document_type,
            document_id=document_id,
            document_subtype=document_subtype,
            confidence=confidence,
            section_boundaries=section_boundaries,
            page_section_map=page_section_map,
            metadata=metadata,
        )
    
    async def get_section_map_for_chunking(
        self,
        classification_result: DocumentClassificationResult,
    ) -> Dict[int, SectionType]:
        """Convert classification result to canonical section map for chunking.
        
        Uses SectionTypeMapper to ensure consistent taxonomy.
        
        Args:
            classification_result: Result from classify_document
            
        Returns:
            Dict mapping page numbers to canonical SectionType
        """
        from app.utils.section_type_mapper import SectionTypeMapper
        
        section_map = {}
        
        for page_num, section_str in classification_result.page_section_map.items():
            # Use canonical mapper to normalize section type
            section_type = SectionTypeMapper.string_to_section_type(section_str)
            section_map[page_num] = section_type
        
        return section_map

