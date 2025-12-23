"""Rule-based page classifier for insurance documents.

This classifier uses keyword patterns and structural heuristics to classify
pages into insurance-specific types without requiring ML models.
"""

import re
from typing import List, Dict, Tuple, Optional

from app.models.page_analysis_models import (
    PageSignals,
    PageClassification,
    PageType
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Module-level singleton instance
_page_classifier_instance: Optional["PageClassifier"] = None


class PageClassifier:
    """Rule-based classifier for insurance document pages.
    
    Uses keyword patterns and structural heuristics to achieve high accuracy
    classification without machine learning models.
    """
    
    # Insurance-specific keyword patterns for each section type
    SECTION_PATTERNS: Dict[PageType, List[str]] = {
        PageType.DECLARATIONS: [
            r'declarations?\s+page',
            r'policy\s+number',
            r'named\s+insured',
            r'policy\s+period',
            r'effective\s+date'
        ],
        PageType.COVERAGES: [
            r'coverage[s]?',
            r'limits?\s+of\s+insurance',
            r'insuring\s+agreement',
            r'covered\s+property',
            r'limits?\s+and?\s+deductibles?'
        ],
        PageType.CONDITIONS: [
            r'conditions?',
            r'policy\s+conditions?',
            r'duties\s+in\s+the\s+event',
            r'general\s+conditions?',
            r'your\s+duties'
        ],
        PageType.EXCLUSIONS: [
            r'exclusions?',
            r'what\s+is\s+not\s+covered',
            r'we\s+do\s+not\s+cover',
            r'this\s+insurance\s+does\s+not\s+apply'
        ],
        PageType.ENDORSEMENT: [
            r'endorsement\s+no\.?',
            r'attached\s+endorsement',
            r'this\s+endorsement\s+changes',
            r'endorsement\s+schedule',
            r'policy\s+change'
        ],
        PageType.SOV: [
            r'schedule\s+of\s+values',
            r'location\s+schedule',
            r'building\s+schedule',
            r'property\s+schedule'
        ],
        PageType.LOSS_RUN: [
            r'loss\s+history',
            r'claims?\s+history',
            r'loss\s+run',
            r'claims?\s+summary'
        ],
        PageType.INVOICE: [
            r'invoice',
            r'amount\s+due',
            r'premium\s+summary',
            r'billing\s+statement'
        ],
        PageType.BOILERPLATE: [
            r'iso\s+properties',
            r'copyright\s+iso',
            r'includes\s+copyrighted\s+material',
            r'commercial\s+general\s+liability\s+cg\s+\d{2}\s+\d{2}',
            r'page\s+\d+\s+of\s+\d+'  # Generic page footer
        ]
    }
    
    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize page classifier.
        
        Args:
            confidence_threshold: Minimum confidence to classify (0.0 to 1.0)
                Pages below this threshold are marked as UNKNOWN
        """
        self.confidence_threshold = confidence_threshold
        logger.info(
            f"Initialized PageClassifier with threshold {confidence_threshold}"
        )
    
    @classmethod
    def get_instance(cls, confidence_threshold: float = 0.7) -> "PageClassifier":
        """Get or create singleton instance of PageClassifier.
        
        Args:
            confidence_threshold: Minimum confidence to classify (0.0 to 1.0)
                Only used on first initialization. Subsequent calls ignore this parameter.
        
        Returns:
            Singleton instance of PageClassifier
        """
        global _page_classifier_instance
        if _page_classifier_instance is None:
            _page_classifier_instance = cls(confidence_threshold)
        return _page_classifier_instance
    
    def classify(self, signals: PageSignals) -> PageClassification:
        """Classify a page based on its signals.
        
        Args:
            signals: PageSignals extracted from the page
            
        Returns:
            PageClassification with type, confidence, and processing decision
        """
        # Combine top lines into searchable text
        top_text = ' '.join(signals.top_lines).lower()
        
        # Try pattern matching first
        page_type, base_confidence = self._match_patterns(top_text)
        
        # Apply structural heuristics to boost confidence
        confidence = self._apply_heuristics(
            page_type, 
            base_confidence, 
            signals
        )
        
        # Determine if page should be processed
        should_process = self._should_process(page_type, confidence)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(page_type, signals, confidence)
        
        classification = PageClassification(
            page_number=signals.page_number,
            page_type=page_type,
            confidence=confidence,
            should_process=should_process,
            reasoning=reasoning
        )
        
        logger.debug(
            f"Page {signals.page_number} classified as {page_type} "
            f"(confidence: {confidence:.2f}, process: {should_process})",
            extra={
                "page_number": signals.page_number,
                "page_type": page_type,
                "confidence": confidence,
                "should_process": should_process
            }
        )
        
        return classification
    
    def _match_patterns(self, text: str) -> Tuple[PageType, float]:
        """Match text against keyword patterns.
        
        Args:
            text: Lowercase text to search
            
        Returns:
            Tuple of (matched PageType, confidence score)
        """
        best_match = PageType.UNKNOWN
        best_score = 0.0
        
        for page_type, patterns in self.SECTION_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matches += 1
            
            # Calculate score based on match ratio
            if matches > 0:
                score = min(matches / len(patterns) + 0.5, 1.0)
                if score > best_score:
                    best_score = score
                    best_match = page_type
        
        return best_match, best_score
    
    def _apply_heuristics(
        self, 
        page_type: PageType, 
        base_confidence: float,
        signals: PageSignals
    ) -> float:
        """Apply structural heuristics to adjust confidence.
        
        Args:
            page_type: Initially classified page type
            base_confidence: Base confidence from pattern matching
            signals: Page signals
            
        Returns:
            Adjusted confidence score
        """
        confidence = base_confidence
        
        # Heuristic 1: First 5 pages likely to be important
        if signals.page_number <= 5:
            confidence = min(confidence + 0.15, 1.0)
        
        # Heuristic 2: High text density suggests content pages
        if signals.text_density > 0.7:
            confidence = min(confidence + 0.10, 1.0)
        
        # Heuristic 3: Large font sizes suggest headers/important sections
        if signals.max_font_size and signals.max_font_size > 18:
            confidence = min(confidence + 0.10, 1.0)
        
        # Heuristic 4: Tables suggest SOV or Loss Run
        if signals.has_tables and page_type in [PageType.SOV, PageType.LOSS_RUN]:
            confidence = min(confidence + 0.15, 1.0)
        
        # Heuristic 5: Very low text density suggests boilerplate or blank
        if signals.text_density < 0.2:
            if page_type == PageType.BOILERPLATE:
                confidence = min(confidence + 0.10, 1.0)
        
        return round(confidence, 3)
    
    def _should_process(self, page_type: PageType, confidence: float) -> bool:
        """Determine if a page should be processed.
        
        Only process high-value insurance sections.
        
        Args:
            page_type: Classified page type
            confidence: Classification confidence
            
        Returns:
            True if page should undergo full OCR and extraction
        """
        # Never process duplicates or boilerplate
        if page_type in [PageType.DUPLICATE, PageType.BOILERPLATE]:
            return False
        
        # Always process key sections (even with low confidence)
        key_sections = [
            PageType.DECLARATIONS,
            PageType.COVERAGES,
            PageType.ENDORSEMENT
        ]
        if page_type in key_sections:
            return True
        
        # Process table sections (SOV, Loss Run)
        table_sections = [
            PageType.SOV,
            PageType.LOSS_RUN,
            PageType.INVOICE
        ]
        if page_type in table_sections:
            return True
        
        # Process conditions and exclusions only with high confidence
        secondary_sections = [
            PageType.CONDITIONS,
            PageType.EXCLUSIONS
        ]
        if page_type in secondary_sections and confidence >= self.confidence_threshold:
            return True
        
        # Skip unknown pages by default (aggressive filtering)
        # Only process if on early pages (1-5) which are typically important
        if page_type == PageType.UNKNOWN and confidence >= 0.8:
            return True
        
        # Skip low-confidence and unknown pages
        return False
    
    def _generate_reasoning(
        self, 
        page_type: PageType, 
        signals: PageSignals,
        confidence: float
    ) -> str:
        """Generate human-readable reasoning for classification.
        
        Args:
            page_type: Classified page type
            signals: Page signals
            confidence: Classification confidence
            
        Returns:
            Reasoning string
        """
        reasons = []
        
        # Add pattern match reason
        if confidence > 0.5:
            reasons.append(f"Matched {page_type.value} keywords")
        
        # Add structural reasons
        if signals.page_number <= 5:
            reasons.append("early page")
        
        if signals.has_tables:
            reasons.append("contains tables")
        
        if signals.text_density > 0.7:
            reasons.append("high text density")
        elif signals.text_density < 0.2:
            reasons.append("low text density")
        
        if signals.max_font_size and signals.max_font_size > 18:
            reasons.append("large headers")
        
        if not reasons:
            reasons.append("no strong indicators")
        
        return ", ".join(reasons)
