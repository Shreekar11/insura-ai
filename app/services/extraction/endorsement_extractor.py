"""Endorsement extraction service.

This service extracts structured endorsement/amendment information from
insurance policy documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EndorsementItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EndorsementExtractor(BaseExtractor):
    """Extracts endorsement/amendment information from documents.
    
    This service identifies policy endorsements and extracts structured
    information about policy changes, additions, and modifications.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    ENDORSEMENT_EXTRACTION_PROMPT = """You are an expert at extracting endorsement and policy amendment information from insurance documents.

Analyze the following text and extract ALL endorsement information.

**Each endorsement should include:**
- endorsement_number: Endorsement identifier
- policy_number: Associated policy number
- effective_date: Endorsement effective date (YYYY-MM-DD format)
- change_type: Type of change (Addition, Deletion, Modification, Cancellation, etc.)
- description: Description of the change or endorsement
- premium_change: Premium impact (positive for increase, negative for decrease)
- coverage_changes: JSON object describing coverage modifications (e.g., {"added": ["Equipment Breakdown"], "removed": [], "modified": {"deductible": 10000}})

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "endorsement_number": "END-001",
    "policy_number": "POL-2024-001",
    "effective_date": "2024-06-01",
    "change_type": "Addition",
    "description": "Added Equipment Breakdown coverage",
    "premium_change": 500.00,
    "coverage_changes": {
      "added": ["Equipment Breakdown"],
      "removed": [],
      "modified": {}
    }
  }
]

**Important:**
- Extract ALL endorsements from the document
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
- Premium changes can be positive (increase) or negative (decrease)
- coverage_changes should be a JSON object
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for endorsement extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.ENDORSEMENT_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[EndorsementItem]:
        """Extract endorsement items from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[EndorsementItem]: Extracted endorsement items
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for endorsement extraction")
            return []
        
        LOGGER.info(
            "Starting endorsement extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            endorsement_data = await self._call_llm_api(text)
            
            # Create EndorsementItem records
            endorsement_items = []
            for item_data in endorsement_data:
                endorsement_item = await self._create_endorsement_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                endorsement_items.append(endorsement_item)
            
            LOGGER.info(
                f"Extracted {len(endorsement_items)} endorsement items",
                extra={"document_id": str(document_id)}
            )
            
            return endorsement_items
            
        except Exception as e:
            LOGGER.error(
                f"Endorsement extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_endorsement_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> EndorsementItem:
        """Create EndorsementItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            EndorsementItem: Created database record
        """
        endorsement_item = EndorsementItem(
            document_id=document_id,
            chunk_id=chunk_id,
            endorsement_number=item_data.get("endorsement_number"),
            policy_number=item_data.get("policy_number"),
            effective_date=self._parse_date(item_data.get("effective_date")),
            change_type=item_data.get("change_type"),
            description=item_data.get("description"),
            premium_change=self._to_decimal(item_data.get("premium_change")),
            coverage_changes=item_data.get("coverage_changes"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(endorsement_item)
        await self.session.flush()
        
        return endorsement_item
