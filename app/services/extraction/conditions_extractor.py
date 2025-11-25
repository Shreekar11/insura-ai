"""Conditions extraction service.

This service extracts policy conditions from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConditionItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ConditionsExtractor(BaseExtractor):
    """Extracts policy conditions from documents.
    
    This service identifies and extracts structured information about
    policy conditions, exclusions, and limitations.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    CONDITIONS_EXTRACTION_PROMPT = """You are an expert at extracting policy conditions from insurance documents.

Analyze the following text and extract ALL policy conditions, limitations, and requirements.

**Each condition should include:**
- condition_type: Type of condition (e.g., "Coverage Condition", "Claim Condition", "General Condition")
- title: Brief title or heading of the condition
- description: Full description of the condition
- applies_to: What the condition applies to (e.g., specific coverage, entire policy)
- requirements: List of specific requirements or actions needed
- consequences: What happens if condition is not met
- reference: Section or clause reference number

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "condition_type": "Coverage Condition",
    "title": "Duty to Report Claims",
    "description": "The insured must report all claims within 30 days of occurrence",
    "applies_to": "All Coverages",
    "requirements": ["Report within 30 days", "Provide written notice", "Include all relevant details"],
    "consequences": "Failure to report may result in denial of claim",
    "reference": "Section IV, Clause 2"
  }
]

**Important:**
- Extract ALL conditions from the document
- Use null for missing values
- Be comprehensive in capturing requirements
- Include both explicit and implied conditions
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for conditions extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.CONDITIONS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[ConditionItem]:
        """Extract conditions from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[ConditionItem]: Extracted conditions
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for conditions extraction")
            return []
        
        LOGGER.info(
            "Starting conditions extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            conditions_data = await self._call_llm_api(text)
            
            # Create ConditionItem records
            conditions = []
            for item_data in conditions_data:
                condition = await self._create_condition_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                conditions.append(condition)
            
            LOGGER.info(
                f"Extracted {len(conditions)} conditions",
                extra={"document_id": str(document_id)}
            )
            
            return conditions
            
        except Exception as e:
            LOGGER.error(
                f"Conditions extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []

    async def _create_condition_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> ConditionItem:
        """Create ConditionItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            ConditionItem: Created database record
        """
        condition = ConditionItem(
            document_id=document_id,
            chunk_id=chunk_id,
            condition_type=item_data.get("condition_type"),
            title=item_data.get("title"),
            description=item_data.get("description"),
            applies_to=item_data.get("applies_to"),
            requirements=item_data.get("requirements"),
            consequences=item_data.get("consequences"),
            reference=item_data.get("reference"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(condition)
        await self.session.flush()
        
        return condition
