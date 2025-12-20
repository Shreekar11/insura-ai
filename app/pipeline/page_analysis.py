"""Phase 0: Page Analysis facade.

Combines PageAnalyzer, PageClassifier, and DuplicateDetector into a single interface.
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
    def __init__(self, session: AsyncSession):
        self.session = session
        self.analyzer = PageAnalyzer()
        self.classifier = PageClassifier()
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

