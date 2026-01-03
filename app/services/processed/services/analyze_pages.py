"""Analyze pages service - extracts signals and classifies pages."""

from uuid import UUID
from app.services.processed.contracts import PageManifest, DocumentProfile

# Wraps existing services
from app.services.processed.services.analysis.lightweight_page_analyzer import LightweightPageAnalyzer
from app.services.processed.services.analysis.page_classifier import PageClassifier
from app.services.processed.services.analysis.document_profile_builder import DocumentProfileBuilder


class AnalyzePagesService:
    """Service for page-level analysis and classification."""
    
    def __init__(self):
        self._analyzer = LightweightPageAnalyzer.get_instance()
        self._classifier = PageClassifier.get_instance()
        self._profile_builder = DocumentProfileBuilder()
    
    async def execute(self, document_id: UUID) -> PageManifest:
        """Analyze all pages and build document profile."""
        # Note: In real implementation, this would orchestrate the existing 
        # page analysis pipeline components. 
        # For now, this is a conceptual wrapper around the existing logic
        # that will be called by the Facade or Temporal activities.
        
        # This is a thin wrapper that will eventually house the logic 
        # currently in temporal activities, but decoupled from Temporal.
        pass
