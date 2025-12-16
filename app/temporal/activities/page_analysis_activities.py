"""Page analysis activities for Temporal workflows.

These activities extract page signals, classify pages, and create manifests
to determine which pages should undergo full OCR processing.
"""

from temporalio import activity
from typing import List, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.repositories.document_repository import DocumentRepository
from app.repositories.page_analysis_repository import PageAnalysisRepository
from app.services.pipeline.page_analyzer import PageAnalyzer
from app.services.pipeline.page_classifier import PageClassifier
from app.services.pipeline.duplicate_detector import DuplicateDetector
from app.models.page_analysis_models import PageSignals, PageClassification, PageType
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_page_signals(document_id: str) -> List[Dict]:
    """Extract lightweight signals from all pages using Docling's selective extraction.
    
    Args:
        document_id: Document UUID string
        
    Returns:
        List of page signals dictionaries
    """
    activity.logger.info(
        f"Starting page signal extraction for document {document_id}",
        extra={"document_id": document_id}
    )
    logger.info(f"[TERMINAL] Starting page signal extraction for document {document_id}")
    
    try:
        # Get database session
        async for session in get_async_session():
            # Get document to retrieve file_path (which contains the PDF URL)
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document.file_path:
                raise ValueError(f"Document {document_id} has no file path")
        
            # Determine if it's a URL or local file
            document_url = document.file_path
            
            # Initialize analyzer
            analyzer = PageAnalyzer()
            
            logger.info(
                f"Starting page and signal extraction for document {document_id}",
                extra={"document_url": document_url}
            )
            
            try:
                # Perform full document analysis in one pass
                page_signals_list = analyzer.analyze_document(document_url)
                
                # Initialize repository for persistence
                page_repo = PageAnalysisRepository(session)

                # Save all signals to database
                for page_signals in page_signals_list:
                    await page_repo.save_page_signals(UUID(document_id), page_signals)
                
                # Commit all signal saves
                await session.commit()
                
                serialized_signals = [signals.dict() for signals in page_signals_list]
                
                activity.logger.info(
                    f"Completed signal extraction: {len(serialized_signals)} pages processed",
                    extra={"document_id": document_id, "total_pages": len(serialized_signals)}
                )
                logger.info(f"[TERMINAL] ✓ Signal extraction complete for {document_id} ({len(serialized_signals)} pages)")
                
                return serialized_signals

            except Exception as e:
                activity.logger.error(
                    f"Signal extraction logic failed: {e}",
                    extra={"document_id": document_id},
                    exc_info=True
                )
                logger.error(f"[TERMINAL] ✗ Signal extraction logic failed: {e}")
                raise
            
    except Exception as e:
        activity.logger.error(
            f"Page signal extraction activity failed: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        logger.error(f"[TERMINAL] ✗ Signal extraction activity failed: {e}")
        raise


@activity.defn
async def classify_pages(document_id: str, page_signals: List[Dict]) -> List[Dict]:
    """Classify pages using rule-based classifier with duplicate detection.
    
    Args:
        document_id: Document UUID string
        page_signals: List of page signals dictionaries
        
    Returns:
        List of page classification dictionaries
    """
    activity.logger.info(f"Starting page classification for {len(page_signals)} pages")
    logger.info(f"[TERMINAL] Classifying {len(page_signals)} pages...")
    
    try:
        # Initialize classifier and duplicate detector
        classifier = PageClassifier()
        detector = DuplicateDetector()
        
        # Get database session
        async for session in get_async_session():
            page_repo = PageAnalysisRepository(session)
            
            classifications = []
            page_type_counts = {}
            duplicates_found = 0
            
            for signals_dict in page_signals:
                signals = PageSignals(**signals_dict)
                
                # Check for duplicates first
                is_dup, dup_of = detector.is_duplicate(signals)
                if is_dup:
                    classification = PageClassification(
                        page_number=signals.page_number,
                        page_type=PageType.DUPLICATE,
                        confidence=1.0,
                        should_process=False,
                        duplicate_of=dup_of,
                        reasoning=f"Duplicate of page {dup_of}"
                    )
                    duplicates_found += 1
                    activity.logger.debug(
                        f"Page {signals.page_number} is duplicate of page {dup_of}"
                    )
                else:
                    classification = classifier.classify(signals)
                    activity.logger.debug(
                        f"Page {signals.page_number}: {classification.page_type} "
                        f"(confidence: {classification.confidence:.2f})"
                    )
                
                # Save classification to database
                await page_repo.save_page_classification(UUID(document_id), classification)
                
                # Track page type counts
                page_type = classification.page_type
                page_type_counts[page_type] = page_type_counts.get(page_type, 0) + 1
                
                classifications.append(classification.dict())
            
            # Commit all classifications
            await session.commit()
            
            # Log summary statistics
            pages_to_process = sum(1 for c in classifications if c['should_process'])
            pages_skipped = len(classifications) - pages_to_process
            
            activity.logger.info(
                f"Classification complete: {pages_to_process} pages to process, "
                f"{pages_skipped} pages skipped ({duplicates_found} duplicates)",
                extra={
                    "total_pages": len(classifications),
                    "pages_to_process": pages_to_process,
                    "pages_skipped": pages_skipped,
                    "duplicates": duplicates_found,
                    "page_type_distribution": page_type_counts
                }
            )
            
            logger.info(
                f"[TERMINAL] ✓ Classification complete:\n"
                f"  - Total pages: {len(classifications)}\n"
                f"  - To process: {pages_to_process} ({(pages_to_process/len(classifications))*100:.1f}%)\n"
                f"  - Skipped: {pages_skipped} ({(pages_skipped/len(classifications))*100:.1f}%)\n"
                f"  - Duplicates: {duplicates_found}\n"
                f"  - Page types: {page_type_counts}"
            )
            
            return classifications
            
    except Exception as e:
        activity.logger.error(
            f"Page classification failed: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        logger.error(f"[TERMINAL] ✗ Classification failed: {e}")
        raise


@activity.defn
async def create_page_manifest(
    document_id: str,
    classifications: List[Dict]
) -> Dict:
    """Create and persist page manifest to database.
    
    Args:
        document_id: Document UUID string
        classifications: List of classification dictionaries
        
    Returns:
        Page manifest dictionary
    """
    activity.logger.info(f"Creating page manifest for document {document_id}")
    logger.info(f"[TERMINAL] Creating page manifest for {document_id}...")
    
    try:
        # Get database session
        async for session in get_async_session():
            from app.models.page_analysis_models import PageManifest
            
            pages_to_process = [
                c['page_number'] for c in classifications 
                if c['should_process']
            ]
            pages_skipped = [
                c['page_number'] for c in classifications 
                if not c['should_process']
            ]
            
            manifest = PageManifest(
                document_id=UUID(document_id),
                total_pages=len(classifications),
                pages_to_process=pages_to_process,
                pages_skipped=pages_skipped,
                classifications=[PageClassification(**c) for c in classifications]
            )
            
            # Persist to database
            page_repo = PageAnalysisRepository(session)
            await page_repo.save_manifest(manifest)
            
            activity.logger.info(
                f"Page manifest saved to database",
                extra={
                    "document_id": document_id,
                    "total_pages": manifest.total_pages,
                    "processing_ratio": manifest.processing_ratio,
                    "pages_to_process": len(pages_to_process),
                    "pages_skipped": len(pages_skipped)
                }
            )
            
            logger.info(
                f"[TERMINAL] ✓ Page manifest saved:\n"
                f"  - Document ID: {document_id}\n"
                f"  - Processing ratio: {manifest.processing_ratio:.1%}\n"
                f"  - Pages to OCR: {pages_to_process}\n"
                f"  - Pages skipped: {len(pages_skipped)}"
            )
            
            return manifest.dict()
            
    except Exception as e:
        activity.logger.error(
            f"Failed to save page manifest: {e}",
            extra={"document_id": document_id},
            exc_info=True
        )
        logger.error(f"[TERMINAL] ✗ Failed to save manifest: {e}")
        raise
