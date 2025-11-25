"""Coverages extraction service.

This service extracts coverage information from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CoverageItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class CoveragesExtractor(BaseExtractor):
    """Extracts coverage information from documents.
    
    This service identifies and extracts structured information about
    insurance coverages, limits, and deductibles.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    COVERAGES_EXTRACTION_PROMPT = """You are an expert at extracting coverage information from insurance documents.

Analyze the following text and extract ALL coverage information.

**Each coverage should include:**
- coverage_name: Name of the coverage (e.g., "Building Coverage", "General Liability")
- coverage_type: Type/category (e.g., "Property", "Liability", "Auto")
- limit_amount: Coverage limit amount
- deductible_amount: Deductible amount
- premium_amount: Premium for this coverage
- description: Description of what is covered
- sub_limits: JSON object with any sub-limits (e.g., {"theft": 50000, "flood": 100000})
- exclusions: List of specific exclusions for this coverage
- conditions: List of conditions that apply to this coverage
- per_occurrence: Whether limit is per occurrence (true/false)
- aggregate: Whether there's an aggregate limit (true/false)

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "coverage_name": "Commercial Property - Building",
    "coverage_type": "Property",
    "limit_amount": 5000000,
    "deductible_amount": 5000,
    "premium_amount": 12500,
    "description": "Covers direct physical loss or damage to buildings",
    "sub_limits": {
      "theft": 50000,
      "flood": 100000
    },
    "exclusions": ["Wear and tear", "Intentional damage"],
    "conditions": ["Must maintain fire suppression system"],
    "per_occurrence": true,
    "aggregate": false
  }
]

**Important:**
- Extract ALL coverages from the document
- Use null for missing values
- Ensure numeric values are numbers, not strings
- Include both primary and additional coverages
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for coverages extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.COVERAGES_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[CoverageItem]:
        """Extract coverages from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[CoverageItem]: Extracted coverages
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for coverages extraction")
            return []
        
        LOGGER.info(
            "Starting coverages extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            coverages_data = await self._call_llm_api(text)
            
            # Create CoverageItem records
            coverages = []
            for item_data in coverages_data:
                coverage = await self._create_coverage_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                coverages.append(coverage)
            
            LOGGER.info(
                f"Extracted {len(coverages)} coverages",
                extra={"document_id": str(document_id)}
            )
            
            return coverages
            
        except Exception as e:
            LOGGER.error(
                f"Coverages extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []

    async def _create_coverage_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> CoverageItem:
        """Create CoverageItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            CoverageItem: Created database record
        """
        coverage = CoverageItem(
            document_id=document_id,
            chunk_id=chunk_id,
            coverage_name=item_data.get("coverage_name"),
            coverage_type=item_data.get("coverage_type"),
            limit_amount=self._to_decimal(item_data.get("limit_amount")),
            deductible_amount=self._to_decimal(item_data.get("deductible_amount")),
            premium_amount=self._to_decimal(item_data.get("premium_amount")),
            description=item_data.get("description"),
            sub_limits=item_data.get("sub_limits"),
            exclusions=item_data.get("exclusions"),
            conditions=item_data.get("conditions"),
            per_occurrence=item_data.get("per_occurrence"),
            aggregate=item_data.get("aggregate"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(coverage)
        await self.session.flush()
        
        return coverage
