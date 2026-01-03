"""Processed Stage Facade - coordinates page analysis, OCR, tables, and chunking."""

from uuid import UUID
from typing import Optional, List
from app.core.base_stage import BaseStage, StageResult, StageStatus

from .services.analyze_pages import AnalyzePagesService
from .services.run_ocr import RunOCRService
from .services.extract_tables import ExtractTablesService
from .services.chunk_pages import ChunkPagesService


class ProcessedStageFacade(BaseStage):
    """
    Processed stage: We can read and structurally understand the document.
    
    Coordinates:
    - Page analysis and classification
    - OCR extraction
    - Table extraction
    - Hybrid chunking
    """
    
    def __init__(
        self,
        analyze_pages: AnalyzePagesService,
        run_ocr: RunOCRService,
        extract_tables: ExtractTablesService,
        chunk_pages: ChunkPagesService,
    ):
        self._analyze = analyze_pages
        self._ocr = run_ocr
        self._tables = extract_tables
        self._chunk = chunk_pages
    
    @property
    def name(self) -> str:
        return "processed"
    
    @property
    def dependencies(self) -> list[str]:
        return []
    
    async def is_complete(self, document_id: UUID) -> bool:
        """Check if stage is complete for document."""
        return await self._chunk.has_chunks(document_id)
    
    async def execute(self, document_id: UUID, *args, **kwargs) -> StageResult:
        """Execute the Processed stage."""
        # 1. Analyze pages
        page_manifest = await self._analyze.execute(document_id)
        
        # 2. Run OCR
        ocr_result = await self._ocr.execute(
            document_id, 
            page_manifest.pages_to_process,
            page_manifest.page_section_map
        )
        
        # 3. Extract tables
        table_result = await self._tables.execute(
            document_id, 
            page_manifest.pages_to_process
        )
        
        # 4. Chunk pages
        chunk_result = await self._chunk.execute(
            document_id, 
            page_manifest.page_section_map
        )
        
        return StageResult(
            status=StageStatus.COMPLETED,
            data={
                "pages_analyzed": page_manifest.total_pages,
                "pages_processed": len(page_manifest.pages_to_process),
                "tables_found": table_result.tables_found,
                "chunks_created": chunk_result.chunk_count,
                "document_type": page_manifest.document_profile.document_type,
            }
        )
