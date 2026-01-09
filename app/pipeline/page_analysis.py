"""Phase 0: Page Analysis facade.

Combines PageAnalyzer, PageClassifier, DuplicateDetector, and DocumentProfileBuilder
into a single interface.

This pipeline uses singleton instances for stateless components (PageAnalyzer, PageClassifier,
DocumentProfileBuilder) to avoid repeated initialization overhead. These singletons are safe
to use in Temporal activities because they are stateless and only contain immutable configuration.

DuplicateDetector maintains per-document state and is instantiated fresh per pipeline
instance, with reset() called at the start of each document classification.

The pipeline now builds a DocumentProfile, deriving document type and section boundaries from rule-based page analysis.
"""

from typing import List, Dict, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.page_analysis_repository import PageAnalysisRepository
from app.services.processed.services.analysis.page_analyzer import PageAnalyzer
from app.services.processed.services.analysis.page_classifier import PageClassifier
from app.services.processed.services.analysis.duplicate_detector import DuplicateDetector
from app.services.processed.services.analysis.document_profile_builder import DocumentProfileBuilder
from app.models.page_analysis_models import (
    PageSignals, 
    PageClassification, 
    PageType, 
    PageManifest,
    DocumentProfile,
    DocumentType,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PageAnalysisPipeline:
    """Pipeline for analyzing and classifying document pages.
    
    This pipeline orchestrates the page analysis workflow:
    1. Extracts lightweight signals from PDF pages
    2. Classifies pages using rule-based patterns
    3. Detects duplicate pages within a document
    4. Builds a document profile
    5. Creates a manifest of pages to process with document context
    
    Note: Uses singleton instances for stateless components to optimize performance
    in Temporal activity execution. Safe for concurrent use in Temporal workers.
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize page analysis pipeline.
        
        Args:
            session: Database session for persisting analysis results
            
        Note:
            - PageAnalyzer, PageClassifier, and DocumentProfileBuilder use singleton instances (stateless)
            - DuplicateDetector is created fresh per pipeline instance (stateful per document)
        """
        self.session = session
        # Singleton instances for stateless components
        self.analyzer = PageAnalyzer.get_instance()
        self.classifier = PageClassifier.get_instance()
        self.profile_builder = DocumentProfileBuilder.get_instance()
        self.detector = DuplicateDetector()
        self.repository = PageAnalysisRepository(session)

    async def extract_signals(self, document_id: UUID, document_url: str) -> List[PageSignals]:
        """Extract lightweight signals from all pages (Legacy - using PDF)."""
        page_signals_list = await self.analyzer.analyze_document(document_url)
        
        # Save signals to database
        for signals in page_signals_list:
            await self.repository.save_page_signals(document_id, signals)
            
        return page_signals_list

    async def extract_signals_from_markdown(
        self, 
        document_id: UUID, 
        pages: List[tuple[str, int]]
    ) -> Tuple[List[PageSignals], DocumentType, float]:
        """Extract signals from already extracted markdown pages.
        
        Args:
            document_id: Document UUID
            pages: List of (markdown_content, page_number) tuples
            
        Returns:
            Tuple of (PageSignals list, document_type, confidence)
        """
        # Combine all content for document type detection
        all_content = " ".join(content for content, _ in pages)
        doc_type, confidence = self.analyzer.markdown_analyzer.detect_document_type(all_content)

        page_signals_list = self.analyzer.analyze_markdown_batch(pages)
        
        # Save signals to database
        for signals in page_signals_list:
            await self.repository.save_page_signals(document_id, signals)
            
        return page_signals_list, doc_type, confidence

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

    async def build_document_profile(
        self, 
        document_id: UUID, 
        classifications: List[PageClassification]
    ) -> DocumentProfile:
        """Build document profile from page classifications.
        
        This builds a document profile by deriving document type and section boundaries from rule-based page analysis.
        
        Args:
            document_id: Document UUID
            classifications: List of page classifications
            
        Returns:
            DocumentProfile with document type, section boundaries, and page map
        """
        profile = self.profile_builder.build_profile(document_id, classifications)
        
        LOGGER.info(
            f"Built document profile for {document_id}",
            extra={
                "document_type": profile.document_type.value,
                "confidence": profile.confidence,
                "section_count": len(profile.section_boundaries),
            }
        )
        
        return profile

    async def create_manifest(
        self, 
        document_id: UUID, 
        classifications: List[PageClassification],
        document_profile: DocumentProfile = None,
    ) -> PageManifest:
        """Create and persist page manifest with document profile.
        
        Args:
            document_id: Document UUID
            classifications: List of page classifications
            document_profile: Optional pre-built document profile
            
        Returns:
            PageManifest with document context for downstream processing
        """
        pages_to_process = [c.page_number for c in classifications if c.should_process]
        pages_skipped = [c.page_number for c in classifications if not c.should_process]
        
        # Build document profile if not provided
        if document_profile is None:
            document_profile = await self.build_document_profile(document_id, classifications)
        
        # Build page section map from profile
        page_section_map = document_profile.page_section_map
        
        manifest = PageManifest(
            document_id=document_id,
            total_pages=len(classifications),
            pages_to_process=pages_to_process,
            pages_skipped=pages_skipped,
            classifications=classifications,
            document_profile=document_profile,
            page_section_map=page_section_map,
        )
        
        await self.repository.save_manifest(manifest)
        
        LOGGER.info(
            f"Created manifest for {document_id} with document profile",
            extra={
                "total_pages": manifest.total_pages,
                "pages_to_process": len(pages_to_process),
                "document_type": document_profile.document_type.value,
                "section_count": len(document_profile.section_boundaries),
            }
        )
        
        return manifest

