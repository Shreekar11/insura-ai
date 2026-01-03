"""Extract tables service - extracts structural tables from pages."""

from uuid import UUID
from typing import List
from app.services.processed.contracts import TableResult
from app.services.processed.services.table.table_extraction_service import TableExtractionService


class ExtractTablesService:
    """Service for extracting tables from document pages."""
    
    def __init__(self, table_service=TableExtractionService):
        self._table_service = table_service
    
    async def execute(
        self, 
        document_id: UUID, 
        pages_to_process: List[int]
    ) -> TableResult:
        """Extract tables from specified pages."""
        # Implementation would call self._table_service
        pass
