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
    # Patterns are ranked by specificity - more specific patterns have higher match scores
    SECTION_PATTERNS: Dict[PageType, List[str]] = {
        PageType.DECLARATIONS: [
            r'declarations?\s+page',
            r'policy\s+declarations?',
            r'common\s+policy\s+declarations?',
            r'policy\s+number\s*[:\-]',
            r'policy\s+number\s*[:\-]?\s*[A-Z0-9\-]+',
            r'named\s+insured\s*[:\-]',
            r'named\s+insured\s+and\s+mailing\s+address',
            r'policy\s+period\s*[:\-]',
            r'policy\s+period\s*:\s*from',
            r'effective\s+date\s*[:\-]',
            r'expiration\s+date\s*[:\-]',
            r'premium\s+[:\-]?\s*\$',
            r'term\s+premium\s*[:\-]?\s*\$',
            r'total\s+[:\-]?\s*\$',
            r'insured\s+name\s*[:\-]',
            r'mailing\s+address\s*[:\-]',
            r'producer\s+and\s+mailing\s+address',
            r'forms?\s+and\s+endorsements?\s+schedule',
            r'coverage\s+summary',
            r'schedule\s+of\s+forms',
            r'limits\s+of\s+liability',
            r'commercial\s+property\s+insurance\s+policy',
            r'insurance\s+policy\s+jacket',
            r'policy\s+schedule',
            r'certificate\s+of\s+insurance',
            r'certificate\s+cum\s+policy\s+schedule',
        ],
        PageType.COVERAGES: [
            r'coverage\s+form',
            r'coverage\s+part',
            r'coverage[s]?\s+[A-Z]\s*[-:]',
            r'limits?\s+of\s+insurance',
            r'insuring\s+agreement',
            r'covered\s+property',
            r'covered\s+causes?\s+of\s+loss',
            r'limits?\s+and\s+deductibles?',
            r'property\s+coverage',
            r'liability\s+coverage',
            r'additional\s+coverage[s]?',
            r'coverage\s+extensions?',
            r'optional\s+coverage[s]?',
            r'special\s+coverage',
            r'blanket\s+coverage',
            r'building\s+coverage',
            r'business\s+personal\s+property',
            r'business\s+income',
            r'extra\s+expense',
        ],
        PageType.CONDITIONS: [
            r'conditions?\s+$',
            r'policy\s+conditions?',
            r'commercial\s+property\s+conditions?',
            r'general\s+conditions?',
            r'loss\s+conditions?',
            r'additional\s+conditions?',
            r'duties\s+in\s+the\s+event',
            r'your\s+duties',
            r'our\s+duties',
            r'transfer\s+of\s+rights',
            r'subrogation',
            r'other\s+insurance',
            r'appraisal',
            r'suit\s+against\s+us',
            r'cancellation',
            r'liberalization',
            r'mortgageholders?',
            r'loss\s+payment',
            r'recovered\s+property',
        ],
        PageType.EXCLUSIONS: [
            r'exclusions?\s*$',
            r'general\s+exclusions?',
            r'property\s+not\s+covered',
            r'what\s+is\s+not\s+covered',
            r'we\s+(do\s+not|will\s+not)\s+cover',
            r'we\s+(do\s+not|will\s+not)\s+pay',
            r'this\s+insurance\s+does\s+not\s+apply',
            r'this\s+policy\s+does\s+not\s+cover',
            r'loss\s+or\s+damage\s+caused\s+by',
            r'the\s+following\s+are\s+excluded',
        ],
        PageType.ENDORSEMENT: [
            r'endorsement\s+no\.?\s*\d*',
            r'endorsement\s+#\s*\d*',
            r'this\s+endorsement\s+(changes|modifies)',
            r'attached\s+to\s+and\s+forms?\s+part',
            r'endorsement\s+schedule',
            r'policy\s+change\s+endorsement',
            r'amendatory\s+endorsement',
            r'additional\s+insured',
            r'waiver\s+of\s+subrogation',
            r'blanket\s+additional\s+insured',
            r'primary\s+and\s+non-?contributory',
        ],
        PageType.SOV: [
            r'schedule\s+of\s+values',
            r'statement\s+of\s+values',
            r'location\s+schedule',
            r'building\s+schedule',
            r'property\s+schedule',
            r'equipment\s+schedule',
            r'scheduled\s+locations?',
            r'tiv\s*[:\-]',
            r'building\s+value',
            r'contents?\s+value',
            r'bi\s*/\s*ee',
        ],
        PageType.LOSS_RUN: [
            r'loss\s+history',
            r'loss\s+run',
            r'loss\s+experience',
            r'claims?\s+history',
            r'claims?\s+summary',
            r'loss\s+summary',
            r'incurred\s+losses?',
            r'paid\s+losses?',
            r'reserved?\s+losses?',
            r'date\s+of\s+loss',
            r'claim\s+number',
            r'claimant',
        ],
        PageType.INVOICE: [
            r'invoice\s*(number|no\.?|#)',
            r'premium\s+invoice',
            r'amount\s+due\s*[:\-]?\s*\$',
            r'total\s+due\s*[:\-]?\s*\$',
            r'premium\s+summary',
            r'billing\s+statement',
            r'payment\s+due',
            r'installment\s+schedule',
        ],
        PageType.DEFINITIONS: [
            r'definitions?\s*$',
            r'section\s+[ivx]+[\.\:]\s*definitions?',
            r'the\s+following\s+definitions?\s+apply',
            r'as\s+used\s+in\s+this\s+policy',
            r'means?\s*[:\-]',
        ],
        PageType.TABLE_OF_CONTENTS: [
            r'table\s+of\s+contents?',
            r'contents?\s*$',
            r'index\s*$',
            r'page\s+number',
        ],
        PageType.BOILERPLATE: [
            r'iso\s+properties',
            r'copyright\s+iso',
            r'includes\s+copyrighted\s+material',
            r'commercial\s+general\s+liability\s+cg\s+\d{2}\s+\d{2}',
            r'cp\s+\d{2}\s+\d{2}',
            r'bp\s+\d{2}\s+\d{2}',
            r'il\s+\d{2}\s+\d{2}',
            r'all\s+rights\s+reserved',
            r'proprietary\s+information',
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
        # Combine top lines into searchable text (for multi-line pattern matching)
        top_text = ' '.join(signals.top_lines).lower()
        
        individual_lines = [line.lower() for line in signals.top_lines]
        
        page_type, base_confidence = self._match_patterns(top_text)
        
        if page_type == PageType.UNKNOWN or base_confidence < 0.5:
            decl_type, decl_confidence = self._match_declarations_patterns(
                top_text, individual_lines
            )
            if decl_confidence > base_confidence:
                page_type = decl_type
                base_confidence = decl_confidence
        
        # Apply structural heuristics to boost confidence
        page_type, confidence = self._apply_heuristics(
            page_type, 
            base_confidence, 
            signals
        )
        
        # Determine if page should be processed
        should_process = self._should_process(page_type, confidence, signals)
        
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
    
    def _match_declarations_patterns(
        self, 
        combined_text: str, 
        individual_lines: List[str]
    ) -> Tuple[PageType, float]:
        """Special pattern matching for declarations pages.
        
        Checks both combined text and individual lines to catch cases where
        field labels and values are on separate lines (common on page 1).
        
        Args:
            combined_text: All top lines joined together
            individual_lines: List of individual lines
            
        Returns:
            Tuple of (PageType, confidence score)
        """
        declarations_patterns = self.SECTION_PATTERNS[PageType.DECLARATIONS]
        matches = 0
        
        # Check combined text
        for pattern in declarations_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                matches += 1
        
        for line in individual_lines:
            for pattern in declarations_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    matches += 1
                    break
        
        if matches > 0:
            score = min(0.3 + (matches * 0.15), 0.95)
            return PageType.DECLARATIONS, score
        
        return PageType.UNKNOWN, 0.0
    
    def _apply_heuristics(
        self, 
        page_type: PageType, 
        base_confidence: float,
        signals: PageSignals
    ) -> Tuple[PageType, float]:
        """Apply structural heuristics to adjust confidence.
        
        Args:
            page_type: Initially classified page type
            base_confidence: Base confidence from pattern matching
            signals: Page signals
            
        Returns:
            Tuple of (Adjusted PageType, Adjusted confidence score)
        """
        confidence = base_confidence
        
        # Extract metadata if available
        meta = signals.additional_metadata or {}
        structure_type = meta.get("structure_type", "standard")
        block_count = meta.get("block_count", 0)
        table_blocks = meta.get("table_block_count", 0)
        
        # Heuristic 1: Page 1 with declarations keywords gets strong boost
        if signals.page_number == 1 and page_type == PageType.DECLARATIONS:
            confidence = min(confidence + 0.40, 1.0)
        elif signals.page_number == 1:
            confidence = min(confidence + 0.25, 1.0)
        elif signals.page_number <= 3:
            confidence = min(confidence + 0.20, 1.0)
        elif signals.page_number <= 5:
            confidence = min(confidence + 0.15, 1.0)
        
        # Heuristic 2: High text density suggests content pages
        if signals.text_density > 0.7:
            confidence = min(confidence + 0.10, 1.0)
            
        # Structure-aware boost: text_heavy pages are likely coverages/conditions
        if structure_type == "text_heavy" and page_type in [PageType.COVERAGES, PageType.CONDITIONS, PageType.EXCLUSIONS, PageType.DEFINITIONS]:
            confidence = min(confidence + 0.15, 1.0)
        
        # Heuristic 3: Large font sizes suggest headers/important sections
        if signals.max_font_size and signals.max_font_size > 18:
            confidence = min(confidence + 0.10, 1.0)
        
        # Heuristic 4: Tables suggest SOV or Loss Run
        if (signals.has_tables or table_blocks > 0) and page_type in [PageType.SOV, PageType.LOSS_RUN]:
            # Extra boost if it's table_heavy
            boost = 0.25 if structure_type == "table_heavy" else 0.15
            confidence = min(confidence + boost, 1.0)
        
        # Heuristic 5: Very low text density suggests boilerplate or blank
        if signals.text_density < 0.2 or (block_count > 0 and block_count < 3):
            if page_type == PageType.BOILERPLATE:
                confidence = min(confidence + 0.15, 1.0)
            elif page_type == PageType.DECLARATIONS and signals.page_number <= 3:
                # Some declarations pages are sparse but labeled
                confidence = min(confidence + 0.15, 1.0)
            elif page_type == PageType.UNKNOWN:
                # Mark sparse unknown as likely boilerplate
                page_type = PageType.BOILERPLATE
                confidence = 0.6
        
        return page_type, round(confidence, 3)
    
    def _should_process(
        self, 
        page_type: PageType, 
        confidence: float,
        signals: PageSignals
    ) -> bool:
        """Determine if a page should be processed.
        
        Only process high-value insurance sections.
        
        Args:
            page_type: Classified page type
            confidence: Classification confidence
            signals: Page signals (for page number check)
            
        Returns:
            True if page should undergo full OCR and extraction
        """
        # Never process duplicates or boilerplate
        if page_type in [PageType.DUPLICATE, PageType.BOILERPLATE]:
            return False
        
        if page_type in [PageType.TABLE_OF_CONTENTS]:
            return False
        
        key_sections = [
            PageType.DECLARATIONS,
            PageType.COVERAGES,
            PageType.ENDORSEMENT
        ]
        if page_type in key_sections:
            if page_type == PageType.DECLARATIONS and signals.page_number <= 3:
                return True
            return True
        
        # Process table sections (SOV, Loss Run)
        table_sections = [
            PageType.SOV,
            PageType.LOSS_RUN,
            PageType.INVOICE
        ]
        if page_type in table_sections:
            return True
        
        secondary_sections = [
            PageType.CONDITIONS,
            PageType.EXCLUSIONS,
            PageType.DEFINITIONS,
        ]
        if page_type in secondary_sections and confidence >= self.confidence_threshold:
            return True
        
        if page_type == PageType.UNKNOWN:
            if signals.page_number == 1:
                return True
            elif signals.page_number <= 3 and confidence >= 0.6:
                return True
            elif confidence >= 0.8:
                return True
        
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
