"""Extract sections service - performs field extraction from sections."""

from uuid import UUID
from typing import List
from app.services.extracted.contracts import SectionExtractionResult
from app.services.extracted.services.extraction.section import SectionExtractionOrchestrator


class ExtractSectionsService:
    """Service for extracting structured data from document sections."""
    
    def __init__(self, extractor: SectionExtractionOrchestrator):
        self._extractor = extractor
    
    async def execute(self, document_id: UUID) -> List[SectionExtractionResult]:
        """Extract fields from all detected sections."""
        # Implementation would call self._extractor
        pass
