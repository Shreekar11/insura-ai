"""Page analysis services for document page classification and profiling.

This package contains services used by the page analysis workflow:
- PageAnalyzer: Extracts lightweight signals from PDF pages
- PageClassifier: Rule-based classifier for insurance document pages
- DuplicateDetector: Detects duplicate pages using MinHash similarity
- DocumentProfileBuilder: Builds document profiles from page classifications
- LightweightPageAnalyzer: Core analyzer using pdfplumber for signal extraction
"""

from app.services.page_analysis.page_analyzer import PageAnalyzer
from app.services.page_analysis.page_classifier import PageClassifier
from app.services.page_analysis.duplicate_detector import DuplicateDetector
from app.services.page_analysis.document_profile_builder import DocumentProfileBuilder
from app.services.page_analysis.lightweight_page_analyzer import LightweightPageAnalyzer

__all__ = [
    "PageAnalyzer",
    "PageClassifier",
    "DuplicateDetector",
    "DocumentProfileBuilder",
    "LightweightPageAnalyzer",
]

