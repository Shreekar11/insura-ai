"""SOV (Statement of Values) extraction service.

This service extracts structured SOV data from insurance documents,
identifying property schedules, building information, and coverage limits.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SOVItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SOVExtractor(BaseExtractor):
    """Extracts Statement of Values data from documents.
    
    This service identifies SOV documents and extracts structured property
    schedule information including locations, buildings, and coverage details.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    SOV_EXTRACTION_PROMPT = """You are an expert at extracting Statement of Values (SOV) data from insurance documents.

Analyze the following text and extract ALL SOV items (property schedules).

**Each SOV item should include:**
- location_number: Location/site identifier
- building_number: Building identifier at location
- description: Property description
- address: Full property address
- construction_type: Construction type (Frame, Masonry, etc.)
- occupancy: Occupancy type (Office, Warehouse, etc.)
- year_built: Year building was constructed
- square_footage: Building square footage
- building_limit: Building coverage limit
- contents_limit: Contents coverage limit
- bi_limit: Business interruption limit
- total_insured_value: Total insured value (TIV)

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "location_number": "001",
    "building_number": "A",
    "description": "Main Office Building",
    "address": "123 Main St, City, ST 12345",
    "construction_type": "Masonry",
    "occupancy": "Office",
    "year_built": 1995,
    "square_footage": 50000,
    "building_limit": 5000000.00,
    "contents_limit": 1000000.00,
    "bi_limit": 500000.00,
    "total_insured_value": 6500000.00
  }
]

**Important:**
- Extract ALL items from tables/schedules
- Use null for missing values
- Ensure numeric values are numbers, not strings
- Parse addresses completely
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for SOV extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.SOV_EXTRACTION_PROMPT
    
    async def extract(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[SOVItem]:
        """Extract SOV items from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[SOVItem]: Extracted SOV items
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for SOV extraction")
            return []
        
        LOGGER.info(
            "Starting SOV extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            sov_data = await self._call_llm_api(text)
            
            # Create SOVItem records
            sov_items = []
            for item_data in sov_data:
                sov_item = await self._create_sov_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                sov_items.append(sov_item)
            
            LOGGER.info(
                f"Extracted {len(sov_items)} SOV items",
                extra={"document_id": str(document_id)}
            )
            
            return sov_items
            
        except Exception as e:
            LOGGER.error(
                f"SOV extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_sov_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> SOVItem:
        """Create SOVItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            SOVItem: Created database record
        """
        sov_item = SOVItem(
            document_id=document_id,
            chunk_id=chunk_id,
            location_number=item_data.get("location_number"),
            building_number=item_data.get("building_number"),
            description=item_data.get("description"),
            address=item_data.get("address"),
            construction_type=item_data.get("construction_type"),
            occupancy=item_data.get("occupancy"),
            year_built=self._to_int(item_data.get("year_built")),
            square_footage=self._to_int(item_data.get("square_footage")),
            building_limit=self._to_decimal(item_data.get("building_limit")),
            contents_limit=self._to_decimal(item_data.get("contents_limit")),
            bi_limit=self._to_decimal(item_data.get("bi_limit")),
            total_insured_value=self._to_decimal(item_data.get("total_insured_value")),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(sov_item)
        await self.session.flush()
        
        return sov_item
