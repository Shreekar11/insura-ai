"""Phase 0: Page Analysis facade.

Combines PageAnalyzer, PageClassifier, and DuplicateDetector into a single interface.

This pipeline uses singleton instances for stateless components (PageAnalyzer, PageClassifier)
to avoid repeated initialization overhead. These singletons are safe to use in Temporal
activities because they are stateless and only contain immutable configuration.

DuplicateDetector maintains per-document state and is instantiated fresh per pipeline
instance, with reset() called at the start of each document classification.
"""

from typing import List, Dict, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.page_analysis_repository import PageAnalysisRepository
from app.services.pipeline.page_analyzer import PageAnalyzer
from app.services.pipeline.page_classifier import PageClassifier
from app.services.pipeline.duplicate_detector import DuplicateDetector
from app.models.page_analysis_models import PageSignals, PageClassification, PageType, PageManifest
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PageAnalysisPipeline:
    """Pipeline for analyzing and classifying document pages.
    
    This pipeline orchestrates the page analysis workflow:
    1. Extracts lightweight signals from PDF pages
    2. Classifies pages using rule-based patterns
    3. Detects duplicate pages within a document
    4. Creates a manifest of pages to process
    
    Note: Uses singleton instances for stateless components to optimize performance
    in Temporal activity execution. Safe for concurrent use in Temporal workers.
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize page analysis pipeline.
        
        Args:
            session: Database session for persisting analysis results
            
        Note:
            - PageAnalyzer and PageClassifier use singleton instances (stateless)
            - DuplicateDetector is created fresh per pipeline instance (stateful per document)
        """
        self.session = session
        # Singleton instances for stateless components
        self.analyzer = PageAnalyzer.get_instance()
        self.classifier = PageClassifier.get_instance()
        self.detector = DuplicateDetector()
        self.repository = PageAnalysisRepository(session)

    async def extract_signals(self, document_id: UUID, document_url: str) -> List[PageSignals]:
        """Extract lightweight signals from all pages."""
        page_signals_list = await self.analyzer.analyze_document(document_url)
        
        # Save signals to database
        for signals in page_signals_list:
            await self.repository.save_page_signals(document_id, signals)
            
        return page_signals_list

    async def classify_pages(self, document_id: UUID, page_signals: List[PageSignals]) -> List[PageClassification]:
        """Classify pages and detect duplicates."""
        self.detector.reset()
        
        classifications = []
        
        for signals in page_signals:
            is_dup, dup_of = self.detector.is_duplicate(signals)
            if is_dup:
                classification = PageClassification(
                    page_number=signals.page_number,
                    page_type=PageType.DUPLICATE,
                    confidence=1.0,
                    should_process=False,
                    duplicate_of=dup_of,
                    reasoning=f"Duplicate of page {dup_of}"
                )
            else:
                classification = self.classifier.classify(signals)
            
            # Save to database
            await self.repository.save_page_classification(document_id, classification)
            classifications.append(classification)
            
        return classifications

    async def create_manifest(self, document_id: UUID, classifications: List[PageClassification]) -> PageManifest:
        """Create and persist page manifest."""
        pages_to_process = [c.page_number for c in classifications if c.should_process]
        pages_skipped = [c.page_number for c in classifications if not c.should_process]
        
        manifest = PageManifest(
            document_id=document_id,
            total_pages=len(classifications),
            pages_to_process=pages_to_process,
            pages_skipped=pages_skipped,
            classifications=classifications
        )
        
        await self.repository.save_manifest(manifest)
        return manifest

