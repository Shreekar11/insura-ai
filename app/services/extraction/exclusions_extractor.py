"""Exclusions extraction service.

This service extracts exclusions from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ExclusionItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ExclusionsExtractor(BaseExtractor):
    """Extracts exclusions from documents.
    
    This service identifies and extracts structured information about
    policy exclusions and limitations.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    EXCLUSIONS_EXTRACTION_PROMPT = """You are an expert at extracting exclusions from insurance documents.

Analyze the following text and extract ALL exclusions and limitations.

**Each exclusion should include:**
- exclusion_type: Type of exclusion (e.g., "General Exclusion", "Coverage-Specific Exclusion")
- title: Brief title or heading of the exclusion
- description: Full description of what is excluded
- applies_to: What coverage(s) the exclusion applies to
- scope: Scope of exclusion ("Total" or "Partial")
- exceptions: Any exceptions to the exclusion
- rationale: Reason for the exclusion (if stated)
- reference: Section or clause reference number

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "exclusion_type": "General Exclusion",
    "title": "War and Military Action",
    "description": "Loss or damage caused by war, invasion, acts of foreign enemies, hostilities, civil war, rebellion, revolution, insurrection or military power",
    "applies_to": "All Coverages",
    "scope": "Total",
    "exceptions": null,
    "rationale": "Catastrophic risk beyond normal underwriting",
    "reference": "Section III, Exclusion 6"
  },
  {
    "exclusion_type": "Coverage-Specific Exclusion",
    "title": "Wear and Tear",
    "description": "Gradual deterioration, wear and tear, rust, corrosion, or mechanical breakdown",
    "applies_to": "Property Coverage",
    "scope": "Total",
    "exceptions": ["Sudden and accidental mechanical breakdown if covered under Equipment Breakdown endorsement"],
    "rationale": "Maintenance is insured's responsibility",
    "reference": "Section I, Exclusion 2(a)"
  }
]

**Important:**
- Extract ALL exclusions from the document
- Use null for missing values
- Be comprehensive in capturing scope and exceptions
- Include both general and specific exclusions
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for exclusions extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.EXCLUSIONS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[ExclusionItem]:
        """Extract exclusions from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[ExclusionItem]: Extracted exclusions
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for exclusions extraction")
            return []
        
        LOGGER.info(
            "Starting exclusions extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            exclusions_data = await self._call_llm_api(text)
            
            # Create ExclusionItem records
            exclusions = []
            for item_data in exclusions_data:
                exclusion = await self._create_exclusion_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                exclusions.append(exclusion)
            
            LOGGER.info(
                f"Extracted {len(exclusions)} exclusions",
                extra={"document_id": str(document_id)}
            )
            
            return exclusions
            
        except Exception as e:
            LOGGER.error(
                f"Exclusions extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []

    async def _create_exclusion_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> ExclusionItem:
        """Create ExclusionItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            ExclusionItem: Created database record
        """
        exclusion = ExclusionItem(
            document_id=document_id,
            chunk_id=chunk_id,
            exclusion_type=item_data.get("exclusion_type"),
            title=item_data.get("title"),
            description=item_data.get("description"),
            applies_to=item_data.get("applies_to"),
            scope=item_data.get("scope"),
            exceptions=item_data.get("exceptions"),
            rationale=item_data.get("rationale"),
            reference=item_data.get("reference"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(exclusion)
        await self.session.flush()
        
        return exclusion
