"""Run OCR service - executes OCR on filtered pages."""

from uuid import UUID
from typing import Dict, List
from app.services.processed.contracts import OCRResult
from app.services.processed.services.ocr.ocr_service import OCRService


class RunOCRService:
    """Service for executing OCR on document pages."""
    
    def __init__(self, ocr_service: OCRService):
        self._ocr_service = ocr_service
    
    async def execute(
        self, 
        document_id: UUID, 
        pages_to_process: List[int],
        page_section_map: Dict[int, str] = None
    ) -> OCRResult:
        """Run OCR on specified pages."""
        # Implementation would call self._ocr_service
        pass
