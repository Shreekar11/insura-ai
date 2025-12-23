"""Page analysis activities for Temporal workflows.

These activities extract page signals, classify pages, and create manifests
to determine which pages should undergo full OCR processing.

PageAnalysisPipeline uses singleton instances for stateless components
(PageAnalyzer, PageClassifier) to optimize initialization overhead.
These singletons are safe for use in Temporal activities because they are stateless
and only contain immutable configuration. Activities run in worker processes, not
workflow code.
"""

from temporalio import activity
from typing import List, Dict
from uuid import UUID

from app.database import get_async_session
from app.pipeline.page_analysis import PageAnalysisPipeline
from app.models.page_analysis_models import PageSignals, PageClassification
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_page_signals(document_id: str) -> List[Dict]:
    """Extract lightweight signals from all pages using Docling's selective extraction."""
    activity.logger.info(
        f"[Phase 0: Page Analysis] Starting page signal extraction for document {document_id}",
        extra={"document_id": document_id}
    )
    
    try:
        async for session in get_async_session():
            # Get document to retrieve file_path
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
        
            pipeline = PageAnalysisPipeline(session)
            signals = await pipeline.extract_signals(UUID(document_id), document.file_path)
            
            await session.commit()
            
            serialized_signals = [s.dict() for s in signals]
            
            activity.logger.info(
                f"[Phase 0: Page Analysis] Completed signal extraction: {len(serialized_signals)} pages processed",
                extra={"document_id": document_id, "total_pages": len(serialized_signals)}
            )
            
            return serialized_signals
            
    except Exception as e:
        activity.logger.error(
            f"Page signal extraction activity failed: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        raise


@activity.defn
async def classify_pages(document_id: str, page_signals: List[Dict]) -> List[Dict]:
    """Classify pages using rule-based classifier with duplicate detection."""
    activity.logger.info(f"[Phase 0: Page Analysis] Starting page classification for {len(page_signals)} pages")
    
    try:
        async for session in get_async_session():
            pipeline = PageAnalysisPipeline(session)
            
            signals_objs = [PageSignals(**s) for s in page_signals]
            classifications = await pipeline.classify_pages(UUID(document_id), signals_objs)
            
            await session.commit()
            
            pages_to_process = sum(1 for c in classifications if c.should_process)
            activity.logger.info(
                f"[Phase 0: Page Analysis] Classification complete: {pages_to_process} pages to process",
                extra={"total_pages": len(classifications), "pages_to_process": pages_to_process}
            )
            
            return [c.dict() for c in classifications]
            
    except Exception as e:
        activity.logger.error(
            f"Page classification failed: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        raise


@activity.defn
async def create_page_manifest(document_id: str, classifications: List[Dict]) -> Dict:
    """Create and persist page manifest to database."""
    activity.logger.info(f"[Phase 0: Page Analysis] Creating page manifest for document {document_id}")
    
    try:
        async for session in get_async_session():
            pipeline = PageAnalysisPipeline(session)
            
            class_objs = [PageClassification(**c) for c in classifications]
            manifest = await pipeline.create_manifest(UUID(document_id), class_objs)
            
            await session.commit()
            
            # Serialize manifest and include computed properties
            manifest_dict = manifest.dict()
            manifest_dict['processing_ratio'] = manifest.processing_ratio
            manifest_dict['cost_savings_estimate'] = manifest.cost_savings_estimate
            
            return manifest_dict
            
    except Exception as e:
        activity.logger.error(
            f"Failed to save page manifest: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        raise
