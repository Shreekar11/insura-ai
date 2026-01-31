"""Rule-based page classifier for insurance documents.

This classifier uses keyword patterns and structural heuristics to classify
pages into insurance-specific types without requiring ML models.

Includes endorsement continuation detection for cross-page tracking via
the EndorsementTracker class.
"""

import re
from typing import List, Dict, Tuple, Optional

from app.models.page_analysis_models import (
    PageSignals,
    PageClassification,
    PageType,
    SectionSpan,
    TextSpan,
    DocumentType,
    SemanticRole,
    CoverageEffect,
    ExclusionEffect
)
from app.services.processed.services.analysis.endorsement_tracker import (
    EndorsementTracker,
    EndorsementContext
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
            r'^#?\s*DECLARATIONS?',
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
        ],
        PageType.CERTIFICATE_OF_INSURANCE: [
            r'certificate\s+of\s+insurance',
            r'evidence\s+of\s+property\s+insurance',
            r'certificate\s+holder',
            r'this\s+certificate\s+is\s+issued\s+as\s+a\s+matter\s+of\s+information',
            r'acord\s+25',
            r'acord\s+24',
        ],
        PageType.COVERAGES: [
            r'^#?\s*COVERAGES?',
            r'coverages?',
            r'coverage\s+form',
            r'coverage\s+part',
            r'coverage[s]?\s+[A-Z]\s*[-:]',
            r'insuring\s+agreement',
            r'covered\s+property',
            r'covered\s+causes?\s+of\s+loss',
            r'property\s+coverage',
            r'liability\s+coverage',
            r'special\s+coverage',
            r'blanket\s+coverage',
            r'building\s+coverage',
            r'business\s+personal\s+property',
            r'business\s+income',
            r'extra\s+expense',
            r'SECTION\s+[IVX]+\s*[-–—]\s*.*COVERAGES?',
        ],
        PageType.COVERAGE_GRANT: [
            r"SECTION\s+II\s*[-–—]\s*COVERED\s+AUTOS\s+LIABILITY\s+COVERAGE",
            r"SECTION\s+III\s*[-–—]\s*PHYSICAL\s+DAMAGE\s+COVERAGE",
            r"we\s+will\s+pay\s+all\s+sums",
            r"we\s+will\s+pay\s+for\s+loss\s+to",
            r"we\s+will\s+pay",
            r"we\s+will\s+also\s+pay",
        ],
        PageType.COVERAGE_EXTENSION: [
            r'coverage\s+extensions?',
            r'additional\s+coverage[s]?',
            r'optional\s+coverage[s]?',
            r'newly\s+acquired\s+autos',
            r'supplementary\s+payments',
            r'out-of-state\s+coverage\s+extensions',
            r'transportation\s+expenses',
            r'loss\s+of\s+use\s+expenses',
        ],
        PageType.LIMITS: [
            r"LIMIT\s+OF\s+INSURANCE",
            r"the\s+most\s+we\s+will\s+pay",
            r"regardless\s+of\s+the\s+number\s+of",
            r'limits?\s+and\s+deductibles?',
            r'limits?\s+of\s+insurance',
            r'we\s+will\s+pay\s+up\s+to',
        ],
        PageType.INSURED_DEFINITION: [
            r"WHO\s+IS\s+AN\s+INSURED",
            r"the\s+following\s+are\s+insureds?",
        ],
        PageType.CONDITIONS: [
            r'^#?\s*CONDITIONS?',
            r'SECTION\s+[IVX]+\s*[-–—]\s*CONDITIONS?',
            r'GENERAL\s+CONDITIONS',
            r'COMMON\s+POLICY\s+CONDITIONS',
            r'LOSS\s+CONDITIONS',
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
            r'^#?\s*EXCLUSIONS?',
            r'SECTION\s+[IVX]+\s*[-–—]\s*EXCLUSIONS?',
            r'GENERAL\s+EXCLUSIONS',
            r'WHAT\s+IS\s+NOT\s+COVERED',
            r'EXCLUDED\s+CAUSES\s+OF\s+LOSS',
            r'exclusions?',
            r'general\s+exclusions?',
            r'property\s+not\s+covered',
            r'what\s+is\s+not\s+covered',
            r'we\s+(do\s+not|will\s+not)\s+cover',
            r'we\s+(do\s+not|will\s+not)\s+pay',
            r'this\s+insurance\s+does\s+not\s+apply',
            r"we\s+will\s+not\s+pay\s+for\s+[\"']?loss[\"']?",
            r"expected\s+or\s+intended\s+injury",
            r"contractual\b",
            r"workers['\s]compensation",
            r"employee\s+indemnification",
            r"fellow\s+employee",
            r"care\s*,\s*custody\s+or\s+control",
            r"handling\s+of\s+property",
            r"mechanical\s+device",
            r"pollution\b",
            r"war\b",
            r"racing\b",
            r"nuclear\s+hazard",
            r'this\s+policy\s+does\s+not\s+cover',
            r'loss\s+or\s+damage\s+caused\s+by',
            r'the\s+following\s+are\s+excluded',
            r'excluded\s+causes\s+of\s+loss',
            r'not\s+covered',
            r'does\s+not\s+provide\s+coverage',
        ],
        PageType.ENDORSEMENT: [
            r'^#?\s*ENDORSEMENTS?',
            r'endorsements?\s*$',
            r'endorsements?\b',
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
            r'forms?\s+and\s+endorsements?',
            r'form\s+[A-Z]{1,4}\s*[\d\-]{2,}',
        ],
        PageType.SOV: [
            r'^#?\s*SCHEDULE OF VALUES',
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
            r'^#?\s*LOSS RUN REPORT',
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
            r"\"[A-Z][A-Za-z\s]+\"\s+means",
            r"means\s+bodily\s+injury",
            r"means\s+property\s+damage",
        ],
        PageType.TABLE_OF_CONTENTS: [
            r'table\s+of\s+contents?',
            r'contents?\s*$',
            r'index\s*$',
            r'page\s+number',
        ],
        PageType.BOILERPLATE: [
            r'iso\s+properties',
            r'COPYRIGHT',
            r'copyright\s+iso',
            r'includes\s+copyrighted\s+material',
            r'commercial\s+general\s+liability\s+cg\s+\d{2}\s+\d{2}',
            r'cp\s+\d{2}\s+\d{2}',
            r'bp\s+\d{2}\s+\d{2}',
            r'il\s+\d{2}\s+\d{2}',
            r'all\s+rights\s+reserved',
            r'proprietary\s+information',
        ],
        PageType.VEHICLE_DETAILS: [
            r'vehicle\s+details',
            r'particulars\s+of\s+(insured\s+)?vehicle',
            r'schedule\s+of\s+vehicles?',
            r'description\s+of\s+vehicles?',
            r'registration\s+no\.?',
            r'chassis\s+number',
            r'engine\s+number',
            r'make\s*/\s*model',
            r'year\s+of\s+manufacture',
        ],
        PageType.INSURED_DECLARED_VALUE: [
            r'insured\'?s?\s+declared\s+value',
            r'idv\s*$',
            r'idv\s*[:\-]',
            r'sum\s+insured',
            r'total\s+sum\s+insured',
        ],
        PageType.LIABILITY_COVERAGES: [
            r'liability\s+coverage',
            r'third\s+party\s+liability',
            r'personal\s+accident\s+cover',
            r'limits?\s+of\s+liability',
            r'compulsory\s+pa\s+cover',
            r'liability\s+to\s+third\s+parties',
        ],
        PageType.DEDUCTIBLES: [
            r'deductibles?\s+schedule',
            r'deductible\s+amount',
            r'retention\s*[:\-]',
            r'self-?insured\s+retention',
            r'sir\s*[:\-]',
            r'deductible\s+type',
            r'applies\s+to\s+deductible',
        ],
        PageType.PREMIUM: [
            r'premium\s+summary',
            r'premium\s+schedule',
            r'total\s+premium\s*[:\-]?\s*\$',
            r'premium\s+calculation',
            r'taxes\s+and\s+fees',
            r'installment\s+plan',
            r'minimum\s+earned\s+premium',
        ],
        PageType.COVERAGES_CONTEXT: [
            r'scheduled\s+items',
            r'details\s+of\s+coverage',
            r'property\s+information',
            r'description\s+of\s+property',
            r'valuation\s+and\s+coinsurance',
            r'limits\s+and\s+deductibles',
            r"covered\s+auto\s Designation\s+symbols",
            r"item\s+two\s+of\s+the\s+declarations",
            r"symbol\s+description",
        ],
        PageType.ACORD_APPLICATION: [
            r'acord\s+\d{2,4}',
            r'applicant\s+information',
            r'producer\s+information',
            r'requested\s+coverage',
            r'prior\s+carrier',
            r'loss\s+history',
            r'commercial\s+insurance\s+application',
        ],
        PageType.PROPOSAL: [
            r'proposal\s+',
            r'we\s+recommend',
            r'our\s+recommendation',
            r'summary\s+of\s+coverage\s+options',
            r'presented\s+for\s+your\s+review',
            r'insurance\s+proposal',
            r'broker\s+recommendation',
        ]
    }
    # Patterns that indicate this is a base policy form (not an endorsement)
    BASE_POLICY_INDICATORS: List[str] = [
        r"SECTION\s+I[-–—\s]+COVERED\s+AUTOS?",
        r"SECTION\s+II[-–—\s]+.*LIABILITY\s+COVERAGE",
        r"SECTION\s+III[-–—\s]+PHYSICAL\s+DAMAGE",
        r"SECTION\s+IV[-–—\s]+.*CONDITIONS",
        r"SECTION\s+V[-–—\s]+DEFINITIONS",
        r"BUSINESS\s+AUTO\s+COVERAGE\s+FORM",
        r"COMMERCIAL\s+GENERAL\s+LIABILITY\s+FORM",
        r"COMMERCIAL\s+PROPERTY\s+COVERAGE\s+FORM",
    ]
    # High-priority exclusion header patterns (structural, not semantic)
    STRUCTURAL_EXCLUSION_HEADERS: List[str] = [
        r"^##?\s*B\.\s*Exclusions?\s*$",
        r"^##?\s*EXCLUSIONS?\s*$",
        r"^##?\s*\d+\.\s*Exclusions?\s*$",
        r"SECTION\s+[IVX]+\s*[-–—]\s*EXCLUSIONS?",
    ]
    # Table-aware context patterns
    COVERAGE_CONTEXT_TABLE_HEADERS: List[str] = [
        r"covered\s+auto\s+designation\s+symbols?",
        r"description\s+of\s+covered\s+auto\s+designation\s+symbols",
    ]
    # ACORD Certificate of Insurance hard override patterns
    # These patterns are HIGHLY specific to ACORD certificates and should
    # immediately classify the page as CERTIFICATE_OF_INSURANCE
    ACORD_CERTIFICATE_OVERRIDE_PATTERNS: List[str] = [
        r"this\s+certificate\s+is\s+issued\s+as\s+a\s+matter\s+of\s+information",
        r"acord\s+2[45]",  # ACORD 24 (property) or ACORD 25 (liability)
        r"certificate\s+of\s+liability\s+insurance",
        r"certificate\s+of\s+property\s+insurance",
    ]
    # Endorsement header hard override patterns
    # The standard ISO endorsement header should strongly indicate endorsement classification
    ENDORSEMENT_HEADER_OVERRIDE_PATTERNS: List[str] = [
        r"this\s+endorsement\s+changes\s+the\s+policy\.?\s*please\s+read\s+it\s+carefully",
    ]
    # Regex for modifier detection in endorsements (to be deprecated in favor of specific mappings)
    MODIFIER_PATTERNS = {
        "adds_coverage": [r"adds\s+coverage", r"additional\s+coverage", r"extension\s+of\s+coverage"],
        "modifies_coverage": [r"modifies\s+coverage", r"amends\s+coverage", r"changes\s+the\s+policy"],
        "removes_coverage": [r"removes\s+coverage", r"exclusion\s+of", r"deletion\s+of"],
        "limitation": [r"limitation\s+of", r"restrictive\s+endorsement"],
        "notice_requirement": [r"notice\s+requirement", r"reporting\s+provision"],
        "administrative": [r"administrative\s+change", r"notice\s+of\s+information"],
    }
    # Semantic mappings for roles and effects
    SEMANTIC_ROLE_PATTERNS: Dict[SemanticRole, List[str]] = {
        SemanticRole.COVERAGE_MODIFIER: [
            # Existing patterns
            r"adds?\s+coverage", r"additional\s+coverage", r"extension\s+of\s+coverage",
            r"expands?\s+coverage", r"modifies\s+coverage", r"amends?\s+coverage",
            r"changes\s+the\s+policy", r"restores?\s+coverage",
            # Section reference + operation patterns
            r"section\s+(ii|iii|iv)\b.*(is\s+amended|is\s+replaced)",
            r"paragraph\s+[a-z]\.\s+(is|are)\s+(replaced|amended)",
        ],
        SemanticRole.EXCLUSION_MODIFIER: [
            r"removes?\s+coverage", r"exclusion\s+of", r"deletion\s+of",
            r"limitation\s+of", r"restrictive\s+endorsement", r"introduces?\s+exclusion",
            r"narrows?\s+exclusion", r"removes?\s+exclusion",
            r"does\s+not\s+apply\s+to\s+one\s+or\s+more",
            r"exclusion\s+[a-z0-9\.\(\)]+\s+does\s+not\s+apply",
            r"does\s+not\s+apply\s+to.*?(only|unless|provided\s+that|if)",
            r"(the\s+following\s+replaces).*?exclusion",
            r"replaces\s+paragraph\s+[a-z0-9\.\(\)]+\s*,?\s*exclusions?",
            r"only\s+applies\s+if",
            r"only\s+to\s+the\s+extent",
        ],
        SemanticRole.ADMINISTRATIVE_ONLY: [
            r"administrative\s+change", r"notice\s+of\s+information", 
            r"reporting\s+provision", r"notice\s+requirement",
            r"notice\s+of\s+cancellation",
            r"mailing\s+address",
            r"named\s+insured\s+is\s+changed\s+to",
        ]
    }
    # Section reference patterns for higher weighting in semantic detection
    SECTION_REFERENCE_PATTERNS: List[str] = [
        r"section\s+(i{1,3}|iv)",           # SECTION II, III, IV
        r"coverage\s+[a-z](\.|:)",          # Coverage A., Coverage B:
        r"exclusion\s+[a-z0-9\.]+",         # Exclusion B.1
        r"paragraph\s+[a-z0-9]+\.",         # Paragraph A.
    ]
    # Structural exclusion references for higher weighting
    STRUCTURAL_EXCLUSION_PATTERNS: List[str] = [
        r"section\s+iii.*exclusions?",
        r"paragraph\s+b\.3\.,\s+exclusions",
    ]
    COVERAGE_EFFECT_PATTERNS: Dict[CoverageEffect, List[str]] = {
        CoverageEffect.ADDS_COVERAGE: [
            r"adds?\s+coverage", r"additional\s+coverage",
            r"the\s+following\s+(is|are)\s+added\s+to",
            r"is\s+amended\s+to\s+include",
            r"is\s+extended\s+to\s+include",
            r"who\s+is\s+an\s+insured.*?is\s+changed\s+to\s+include",
            r"who\s+is\s+an\s+insured\s+(is|are)\s+(amended|revised|modified)",
            r"include\s+as\s+an\s+.{0,20}insured",
            r"this\s+insurance\s+applies\s+to",
            r"coverage\s+is\s+provided\s+for",
            r"(is\s+)?primary\s+(to\s+)?and\s+non-contributory",
            r"primary\s+and\s+noncontributory",
            r"additional\s+insured",
            r"blanket\s+additional\s+insured",
        ],
        CoverageEffect.EXPANDS_COVERAGE: [
            r"expands?\s+coverage", r"extension\s+of\s+coverage",
            r"endorsement\s+broadens\s+coverage",
            r"this\s+endorsement\s+broadens\s+coverage",
            r"section\s+(ii|iii|iv)\b.*?\b(coverage|insured|supplementary\s+payments)",
            r"the\s+following\s+replaces\s+paragraph",
            r"the\s+following\s+replaces\s+subparagraph",
        ],
        CoverageEffect.LIMITS_COVERAGE: [
            r"limits?\s+coverage", r"limitation\s+of", r"restrictive", r"restricts?\s+coverage",
            # Conditional restriction
            r"applies\s+only\s+if",
            r"only\s+applies\s+when",
            r"subject\s+to\s+the\s+following",
            r"limited\s+to",
            r"not\s+exceed",
            r"no\s+greater\s+than",
            r"but\s+only\s+for\s+damages",
            r"only\s+to\s+the\s+extent",
        ],
        CoverageEffect.RESTORES_COVERAGE: [r"restores?\s+coverage", r"coverage.*?(is\s+)?restored"],
    }
    EXCLUSION_EFFECT_PATTERNS: Dict[ExclusionEffect, List[str]] = {
        ExclusionEffect.INTRODUCES_EXCLUSION: [
            r"introduces?\s+exclusion", r"exclusion\s+of",
            r"adds?\s+(an\s+)?exclusion", r"excludes?\b",
            r"this\s+insurance\s+does\s+not\s+apply\s+to",
            r"coverage\s+does\s+not\s+apply\s+to",
            r"exclusion.*?(is\s+)?added",
        ],
        ExclusionEffect.NARROWS_EXCLUSION: [
            r"narrows?\s+exclusion",
            r"exclusion.*?(is\s+)?narrowed",
            r"exclusion\s+[a-z0-9\.\(\)]+\s+does\s+not\s+apply",
            r"does\s+not\s+apply\s+to.*?(only|unless|provided\s+that|if)",
            r"exclusion\s+[a-z0-9\.]+\s+(is|are)\s+(added|revised|replaced)",
            r"(no|none\s+of\s+the|does\s+not)\s+.*?\bwill\s+apply\b",
        ],
        ExclusionEffect.REMOVES_EXCLUSION: [
            r"removes?\s+exclusion", r"deletion\s+of\s+exclusion",
            r"exclusion.*?(is\s+)?removed",
            r"exclusion.*?is\s+deleted",
            r"is\s+replaced\s+by\s+the\s+following",
            r"deleted\s+and\s+replaced\s+with",
            r"(the\s+following\s+replaces).*?exclusion",
            r"replaces\s+paragraph\s+[a-z0-9\.\(\)]+\s*,?\s*exclusions?",
            r"waives?\s+any\s+right\s+of\s+recovery",
        ],
    }
    
    def __init__(self, confidence_threshold: float = 0.7):
        """Initialize page classifier.

        Args:
            confidence_threshold: Minimum confidence to classify (0.0 to 1.0)
                Pages below this threshold are marked as UNKNOWN
        """
        self.confidence_threshold = confidence_threshold
        self.endorsement_tracker = EndorsementTracker()
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
    
    def _is_acord_certificate(self, text: str) -> bool:
        """Check if text contains ACORD certificate indicators.

        ACORD certificates have very distinctive language that is unambiguous.
        This method provides a hard override before general pattern matching.

        Args:
            text: Lowercase text to check

        Returns:
            True if this is an ACORD certificate
        """
        for pattern in self.ACORD_CERTIFICATE_OVERRIDE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _has_strong_endorsement_header(self, text: str) -> bool:
        """Check if text contains strong endorsement header indicators.

        The standard ISO endorsement header should strongly indicate endorsement
        classification, overriding other potentially matching patterns.

        Args:
            text: Lowercase text to check

        Returns:
            True if this has a strong endorsement header
        """
        for pattern in self.ENDORSEMENT_HEADER_OVERRIDE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def classify(self, signals: PageSignals, doc_type: DocumentType = DocumentType.UNKNOWN) -> PageClassification:
        """Classify a page based on its signals.

        Args:
            signals: PageSignals extracted from the page
            doc_type: Overall document type context (optional)

        Returns:
            PageClassification with type, confidence, and processing decision
        """
        # Combine top lines into searchable text
        top_text = ' '.join(signals.top_lines).lower()
        individual_lines = [line.lower() for line in signals.top_lines]

        # Also check full text for hard overrides if available
        full_text = ' '.join(signals.all_lines).lower() if signals.all_lines else top_text

        # HARD OVERRIDE 1: ACORD Certificate Detection
        # Check FIRST before any other pattern matching - ACORD certificates have
        # very distinctive language and should NEVER be classified as conditions/coverages
        if self._is_acord_certificate(full_text):
            logger.debug(f"Page {signals.page_number}: ACORD certificate hard override triggered")
            return PageClassification(
                page_number=signals.page_number,
                page_type=PageType.CERTIFICATE_OF_INSURANCE,
                confidence=0.98,
                should_process=False,  # Certificates are metadata only - no extraction
                reasoning="ACORD certificate detected: 'THIS CERTIFICATE IS ISSUED AS A MATTER OF INFORMATION' - informational only",
                semantic_role=SemanticRole.INFORMATIONAL_ONLY,
                coverage_effects=[],
                exclusion_effects=[],
                sections=[
                    SectionSpan(
                        section_type=PageType.CERTIFICATE_OF_INSURANCE,
                        confidence=0.98,
                        span=TextSpan(start_line=1, end_line=len(signals.all_lines) if signals.all_lines else 1),
                        reasoning="ACORD certificate - atomic informational segment",
                        semantic_role=SemanticRole.INFORMATIONAL_ONLY,
                        coverage_effects=[],
                        exclusion_effects=[]
                    )
                ]
            )

        # HARD OVERRIDE 2: Endorsement Header Detection
        # Standard ISO endorsement header should strongly indicate endorsement classification
        if self._has_strong_endorsement_header(full_text):
            logger.debug(f"Page {signals.page_number}: Endorsement header hard override triggered")
            role, cov_effects, excl_effects = self._detect_semantic_intent(full_text)
            return PageClassification(
                page_number=signals.page_number,
                page_type=PageType.ENDORSEMENT,
                confidence=0.95,
                should_process=True,
                reasoning="Endorsement header detected: 'THIS ENDORSEMENT CHANGES THE POLICY. PLEASE READ IT CAREFULLY.'",
                semantic_role=role if role else SemanticRole.COVERAGE_MODIFIER,
                coverage_effects=cov_effects,
                exclusion_effects=excl_effects,
                sections=[
                    SectionSpan(
                        section_type=PageType.ENDORSEMENT,
                        confidence=0.95,
                        span=TextSpan(start_line=1, end_line=len(signals.all_lines) if signals.all_lines else 1),
                        reasoning="Atomic endorsement segment",
                        semantic_role=role if role else SemanticRole.COVERAGE_MODIFIER,
                        coverage_effects=cov_effects,
                        exclusion_effects=excl_effects
                    )
                ]
            )

        # Pass 1: Pattern Matching
        page_type, base_confidence = self._match_patterns(top_text, doc_type=doc_type)
        
        # Special handling for declarations
        if page_type == PageType.UNKNOWN or base_confidence < 0.5:
            decl_type, decl_confidence = self._match_declarations_patterns(
                top_text, individual_lines
            )
            if decl_confidence > base_confidence:
                page_type = decl_type
                base_confidence = decl_confidence
        
        # Pass 2: Heuristics
        page_type, confidence = self._apply_heuristics(
            page_type, 
            base_confidence, 
            signals
        )
        
        # Determine processing gating
        should_process = self._should_process(page_type, confidence, signals)
        
        # Reasoning
        reasoning = self._generate_reasoning(page_type, signals, confidence)
        
        classification = PageClassification(
            page_number=signals.page_number,
            page_type=page_type,
            confidence=confidence,
            should_process=should_process,
            reasoning=reasoning
        )
        # Pass 3: Endorsement/Exclusion/Coverage/Conditions Semantic Intent Detection
        if page_type in {PageType.ENDORSEMENT, PageType.EXCLUSIONS, PageType.COVERAGES, PageType.CONDITIONS}:
            full_text = ' '.join(signals.all_lines).lower() if signals.all_lines else top_text
            role, cov_effects, excl_effects = self._detect_semantic_intent(full_text)
            
            # Only populate if we find meaningful effects or it's an endorsement
            if page_type == PageType.ENDORSEMENT or cov_effects or excl_effects:
                classification.semantic_role = role
                classification.coverage_effects = cov_effects
                classification.exclusion_effects = excl_effects
                classification.should_process = True
        # Pass 3: Multi-section Detection (Atomicity Aware)
        if signals.all_lines:
            spans = self._detect_section_spans(signals.all_lines, initial_type=page_type)
            if spans:
                classification.sections = spans
                # Boost should_process if we found valuable spans
                if any(s.confidence > 0.8 for s in spans):
                    classification.should_process = True
        
        logger.debug(
            f"Page {signals.page_number} classified as {page_type} "
            f"(confidence: {confidence:.2f}, process: {should_process})"
        )

        return classification

    def classify_batch(
        self,
        page_signals_list: List[PageSignals],
        doc_type: DocumentType = DocumentType.UNKNOWN
    ) -> List[PageClassification]:
        """Classify a batch of pages with endorsement continuation awareness.

        This method should be used instead of individual classify() calls
        when processing multi-page documents to enable continuation detection.

        IMPORTANT: Semantic role classification is ONLY applied for POLICY_BUNDLE
        documents. For base POLICY documents (ISO format), pages are treated as
        authoritative sections without semantic projection.

        Args:
            page_signals_list: List of PageSignals for all pages
            doc_type: Document type context (POLICY, POLICY_BUNDLE, etc.)

        Returns:
            List of PageClassification with continuation tracking
        """
        self.endorsement_tracker.reset()
        classifications = []

        # Determine if semantic roles should be applied
        # Only apply semantic classification for POLICY_BUNDLE documents
        apply_semantic_roles = doc_type == DocumentType.POLICY_BUNDLE

        for signals in page_signals_list:
            # First, check for endorsement continuation (only for POLICY_BUNDLE)
            if apply_semantic_roles:
                is_continuation, ctx, cont_conf, cont_reason = \
                    self.endorsement_tracker.check_continuation(signals)
            else:
                is_continuation = False
                ctx = None
                cont_conf = 0.0
                cont_reason = "Semantic roles disabled for base policy"

            if is_continuation and ctx is not None:
                # This is an endorsement continuation
                classification = self._create_continuation_classification(
                    signals, ctx, cont_conf, cont_reason
                )
            else:
                # Standard classification
                classification = self.classify(signals, doc_type)

                # Strip semantic roles for base POLICY documents (except endorsement pages)
                if doc_type == DocumentType.POLICY and classification.page_type != PageType.ENDORSEMENT:
                    classification.semantic_role = None
                    classification.coverage_effects = []
                    classification.exclusion_effects = []

                # If this is a new endorsement and we're tracking, start tracking
                if apply_semantic_roles and classification.page_type == PageType.ENDORSEMENT:
                    if signals.has_endorsement_header or not self.endorsement_tracker.active_context:
                        self.endorsement_tracker.start_endorsement(signals)

            # Special handling for Certificate of Insurance
            # Certificates are informational only - they do NOT modify coverage and
            # should NOT be sent to extraction pipelines
            if classification.page_type == PageType.CERTIFICATE_OF_INSURANCE:
                classification.semantic_role = SemanticRole.INFORMATIONAL_ONLY
                classification.coverage_effects = []
                classification.exclusion_effects = []
                classification.should_process = False  # Metadata only - no extraction

            classifications.append(classification)

        logger.info(
            f"Batch classified {len(classifications)} pages, "
            f"endorsement summary: {self.endorsement_tracker.get_endorsement_summary()}"
        )

        return classifications

    def _create_continuation_classification(
        self,
        signals: PageSignals,
        ctx: EndorsementContext,
        confidence: float,
        reasoning: str
    ) -> PageClassification:
        """Create classification for an endorsement continuation page.

        Args:
            signals: PageSignals for the page
            ctx: EndorsementContext from the tracker
            confidence: Continuation confidence score
            reasoning: Reasoning string for the continuation

        Returns:
            PageClassification marked as continuation
        """
        # Detect semantic role within the continuation
        full_text = ' '.join(signals.all_lines).lower() if signals.all_lines else ''
        role, cov_effects, excl_effects = self._detect_semantic_intent(full_text)

        return PageClassification(
            page_number=signals.page_number,
            page_type=PageType.ENDORSEMENT,
            confidence=confidence,
            should_process=True,  # CRITICAL: Always process endorsement pages
            reasoning=f"Endorsement continuation of {ctx.endorsement_id}: {reasoning}",
            sections=[
                SectionSpan(
                    section_type=PageType.ENDORSEMENT,
                    confidence=confidence,
                    span=TextSpan(start_line=1, end_line=len(signals.all_lines) if signals.all_lines else 1),
                    reasoning=f"Continuation of {ctx.endorsement_id}",
                    semantic_role=role,
                    coverage_effects=cov_effects,
                    exclusion_effects=excl_effects,
                )
            ],
            semantic_role=role,
            coverage_effects=cov_effects,
            exclusion_effects=excl_effects,
            # Continuation tracking fields
            is_continuation=True,
            parent_endorsement_id=ctx.endorsement_id,
            endorsement_page_sequence=len(ctx.pages_seen),
        )

    def _match_patterns(self, text: str, doc_type: DocumentType = DocumentType.UNKNOWN) -> Tuple[PageType, float]:
        """Match text against keyword patterns.
        
        Args:
            text: Lowercase text to search
            doc_type: Overall document type context
            
        Returns:
            Tuple of (matched PageType, confidence score)
        """
        best_match = PageType.UNKNOWN
        best_score = 0.0
        
        if doc_type == DocumentType.POLICY or doc_type == DocumentType.UNKNOWN:
            if any(re.search(p, text, re.IGNORECASE) for p in self.STRUCTURAL_EXCLUSION_HEADERS):
                return PageType.EXCLUSIONS, 0.95
            
            if any(re.search(p, text, re.IGNORECASE) for p in self.COVERAGE_CONTEXT_TABLE_HEADERS):
                return PageType.COVERAGES_CONTEXT, 0.90
        match_scores: dict[PageType, tuple[int, float]] = {}
        
        # Priority section types that should be preferred over granular types
        PRIORITY_TYPES = {PageType.DECLARATIONS, PageType.COVERAGES, PageType.ENDORSEMENT}
        # Granular types that map to priority types
        GRANULAR_TYPES = {
            PageType.VEHICLE_DETAILS, 
            PageType.INSURED_DECLARED_VALUE, 
            PageType.LIABILITY_COVERAGES
        }
        
        for page_type, patterns in self.SECTION_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matches += 1
            
            # Calculate score: base bonus of 0.6 for any match, plus unique pattern weight
            if matches > 0:
                score = min(0.6 + (matches * 0.1), 0.95)
                match_scores[page_type] = (matches, score)
                if score > best_score:
                    best_score = score
                    best_match = page_type
        
        if best_match in GRANULAR_TYPES:
            for priority_type in PRIORITY_TYPES:
                if priority_type in match_scores:
                    priority_matches, priority_score = match_scores[priority_type]
                    # If priority type has at least 2 matches, prefer it
                    if priority_matches >= 2:
                        best_match = priority_type
                        best_score = priority_score
                        break
        
        if PageType.ENDORSEMENT in match_scores:
            end_matches, end_score = match_scores[PageType.ENDORSEMENT]
            if best_match in {PageType.COVERAGES, PageType.EXCLUSIONS}:
                # If we have a clear endorsement match, override
                if end_matches >= 1:
                    best_match = PageType.ENDORSEMENT
                    best_score = max(best_score, end_score)
        # Contextual adjustment: If doc is an endorsement or policy, prefer ENDORSEMENT over base sections
        if doc_type in {DocumentType.ENDORSEMENT, DocumentType.POLICY_BUNDLE, DocumentType.POLICY}:
            if best_match in {PageType.COVERAGES, PageType.CONDITIONS, PageType.EXCLUSIONS}:
                if PageType.ENDORSEMENT in match_scores:
                    end_matches, end_score = match_scores[PageType.ENDORSEMENT]
                    # If endorsement has multiple matches or a strong match, prefer it
                    if end_matches >= 2 or end_score >= best_score:
                        best_match = PageType.ENDORSEMENT
                        best_score = max(best_score, end_score)
                    # ALSO override if we have a very specific endorsement pattern (like "THIS ENDORSEMENT CHANGES THE POLICY")
                    if any(re.search(p, text, re.IGNORECASE) for p in [r"this\s+endorsement\s+(changes|modifies)", r"endorsement\s+no\.?\s*\d*"]):
                        best_match = PageType.ENDORSEMENT
                        best_score = max(best_score, end_score)
        
        # Pass 2: Priority Overrides (Mandatory hierarchy)
        # DEFINITIONS > EXCLUSIONS > CONDITIONS > LIMITS > COVERAGE_EXTENSION > COVERAGE_GRANT > COVERAGES
        if best_match != PageType.UNKNOWN:
            priority_order = [
                PageType.DEFINITIONS,
                PageType.EXCLUSIONS,
                PageType.CONDITIONS,
                PageType.LIMITS,
                PageType.COVERAGE_EXTENSION,
                PageType.COVERAGE_GRANT,
                PageType.COVERAGES
            ]
            for p_type in priority_order:
                if p_type in match_scores:
                    # If a higher priority type matched, prefer it if score is close or it's an anchor
                    p_score = match_scores[p_type][1]
                    if p_score >= 0.8 or (p_score > best_score - 0.2):
                        best_match = p_type
                        best_score = max(best_score, p_score)
                        break

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
        """Apply structural heuristics to adjust confidence."""
        confidence = base_confidence
        
        # Heuristic 1: Page 1 or early declarations get strong boost
        if (signals.page_number == 1 or signals.page_number <= 3) and page_type == PageType.DECLARATIONS:
            confidence = min(confidence + 0.40, 1.0)
        elif signals.page_number == 1:
            confidence = min(confidence + 0.25, 1.0)
        elif signals.page_number <= 5:
            confidence = min(confidence + 0.10, 1.0)
        
        # Heuristic 2: Text density boost
        if signals.text_density > 0.7:
            confidence = min(confidence + 0.15, 1.0)
        
        # Heuristic 3: Font size boost for headers
        if signals.max_font_size and signals.max_font_size > 18:
            confidence = min(confidence + 0.10, 1.0)
            
        # Heuristic 4: Table boost for SOV and Loss Run
        if signals.has_tables:
            if page_type in {PageType.SOV, PageType.LOSS_RUN}:
                confidence = min(confidence + 0.15, 1.0)
                
        # Heuristic 5: Metadata-aware boosts
        metadata = signals.additional_metadata or {}
        if metadata.get("structure_type") == "table_heavy" and page_type == PageType.SOV:
            confidence = min(confidence + 0.10, 1.0)
        elif metadata.get("structure_type") == "text_heavy" and page_type in {PageType.COVERAGES, PageType.CONDITIONS}:
            confidence = min(confidence + 0.10, 1.0)
        
        # Heuristic 6: Sparseness check
        if signals.text_density < 0.15:
            if page_type == PageType.UNKNOWN:
                page_type = PageType.BOILERPLATE
                confidence = 0.6
        
        return page_type, round(confidence, 3)
    
    def _should_process(
        self, 
        page_type: PageType, 
        confidence: float,
        signals: PageSignals
    ) -> bool:
        """Atomic gating for downstream processing."""
        if page_type in [PageType.DUPLICATE, PageType.BOILERPLATE, PageType.TABLE_OF_CONTENTS]:
            return False
            
        # First page fallback
        if signals.page_number == 1: return True
        
        if confidence < self.confidence_threshold: return False
        
        return True
    
    def _detect_section_spans(self, lines: List[str], initial_type: PageType = PageType.UNKNOWN) -> List[SectionSpan]:
        """Detect multiple section spans within a page.
        
        Crucial: If initial_type is ENDORSEMENT, this page is ATOMIC.
        We do not subdivide endorsements into base sections.
        """
        if initial_type in {PageType.ENDORSEMENT, PageType.CERTIFICATE_OF_INSURANCE}:
            # Atomic segments that should not be subdivided
            full_text = "\n".join(lines)
            role, cov_effects, excl_effects = self._detect_semantic_intent(full_text)
            return [SectionSpan(
                section_type=initial_type,
                confidence=0.95,
                span=TextSpan(start_line=1, end_line=len(lines)),
                reasoning=f"Atomic {initial_type.value} segment",
                semantic_role=role,
                coverage_effects=cov_effects,
                exclusion_effects=excl_effects
            )]
        spans = []
        current_type = initial_type
        current_start = 1
        current_reasoning = None
        line_count = len(lines)
        
        TARGET_SPAN_TYPES = [
            PageType.DECLARATIONS,
            PageType.COVERAGES,
            PageType.EXCLUSIONS,
            PageType.ENDORSEMENT,
            PageType.DEFINITIONS,
            PageType.CERTIFICATE_OF_INSURANCE,
            PageType.COVERAGES_CONTEXT,
            PageType.VEHICLE_DETAILS,
            PageType.LIABILITY_COVERAGES,
            PageType.INSURED_DECLARED_VALUE,
            PageType.COVERAGE_GRANT,
            PageType.COVERAGE_EXTENSION,
            PageType.LIMITS,
            PageType.INSURED_DEFINITION,
        ]
        
        for i, line in enumerate(lines, 1):
            line_clean = line.strip().lower()
            if len(line_clean) < 5: continue
            
            detected_type = PageType.UNKNOWN
            
            # Sub-pass 1: Check for high-priority structural exclusion headers
            if any(re.search(p, line_clean, re.IGNORECASE) for p in self.STRUCTURAL_EXCLUSION_HEADERS):
                detected_type = PageType.EXCLUSIONS
                # Use the actual line text as reasoning for structural inheritance
                structural_reasoning = f"Structural exclusion header: {line_clean[:50]}"
            
            # Sub-pass 2: Check for coverage context tables
            elif any(re.search(p, line_clean, re.IGNORECASE) for p in self.COVERAGE_CONTEXT_TABLE_HEADERS):
                detected_type = PageType.COVERAGES_CONTEXT
                structural_reasoning = f"Coverage context table: {line_clean[:50]}"
            # Sub-pass 3: Standard pattern matching
            else:
                for p_type in TARGET_SPAN_TYPES:
                    patterns = self.SECTION_PATTERNS.get(p_type, [])
                    for pattern in patterns:
                        # Allow optional prefixes like "## C. " or "11. " before the pattern
                        # We look for Optional #, optional alphanumeric+dot prefix, then the pattern
                        anchor_regex = r'^\s*#*\s*(?:[a-z\d]{1,2}[\.\)]\s+)*' + pattern
                        if re.search(anchor_regex, line_clean, re.IGNORECASE):
                            detected_type = p_type
                            structural_reasoning = f"Section anchor: {line_clean[:50]}"
                            break
                    if detected_type != PageType.UNKNOWN: break
            
            if detected_type != PageType.UNKNOWN and detected_type != current_type:
                if current_type != PageType.UNKNOWN and i - 1 >= current_start:
                    span_text = "\n".join(lines[current_start-1:i-1])
                    role, cov_effects, excl_effects = self._detect_semantic_intent(span_text)
                    # Capture semantic info for endorsements, or if effects are found in base sections
                    capture_semantic = current_type == PageType.ENDORSEMENT or (
                        current_type in {PageType.EXCLUSIONS, PageType.COVERAGES, PageType.CONDITIONS} and (cov_effects or excl_effects)
                    )
                    
                    spans.append(SectionSpan(
                        section_type=current_type,
                        confidence=0.9,
                        span=TextSpan(start_line=current_start, end_line=i-1),
                        reasoning=current_reasoning or f"Previous section {current_type.value}",
                        semantic_role=role if capture_semantic else SemanticRole.UNKNOWN,
                        coverage_effects=cov_effects if capture_semantic else [],
                        exclusion_effects=excl_effects if capture_semantic else []
                    ))
                current_type = detected_type
                current_start = i
                current_reasoning = structural_reasoning
            
            # If we haven't found a reasoning for the current section yet, take the first one we find
            if i == current_start and not current_reasoning and detected_type != PageType.UNKNOWN:
                current_reasoning = structural_reasoning
            elif not current_reasoning and detected_type != PageType.UNKNOWN:
                current_reasoning = structural_reasoning
        
        if current_type != PageType.UNKNOWN:
            span_text = "\n".join(lines[current_start-1:line_count])
            role, cov_effects, excl_effects = self._detect_semantic_intent(span_text)
            # Capture semantic info for endorsements, or if effects are found in base sections
            capture_semantic = current_type == PageType.ENDORSEMENT or (
                current_type in {PageType.EXCLUSIONS, PageType.COVERAGES, PageType.CONDITIONS} and (cov_effects or excl_effects)
            )
            
            spans.append(SectionSpan(
                section_type=current_type,
                confidence=0.9,
                span=TextSpan(start_line=current_start, end_line=line_count),
                reasoning=current_reasoning or "Start of page",
                semantic_role=role if capture_semantic else SemanticRole.UNKNOWN,
                coverage_effects=cov_effects if capture_semantic else [],
                exclusion_effects=excl_effects if capture_semantic else []
            ))
            
        return spans
    def _is_base_policy(self, all_page_texts: List[str]) -> bool:
        """Detect if document is a base policy form (not endorsement bundle).
        
        Checks for multiple canonical ISO policy sections in order.
        """
        combined = " ".join(all_page_texts[:20]).lower() # Check first 20 pages for headers
        section_count = 0
        for pattern in self.BASE_POLICY_INDICATORS:
            if re.search(pattern, combined, re.IGNORECASE):
                section_count += 1
        
        # If we find 3 or more canonical sections, it's highly likely a base policy form
        return section_count >= 3
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
            matched_header = None
            if signals.top_lines:
                first_line = signals.top_lines[0].strip()
                if any(x in first_line.upper() for x in ["SECTION", "FORM", "ENDORSEMENT", "EXCLUSION"]):
                    matched_header = first_line
            
            if matched_header:
                reasons.append(f"Matched {page_type.value} header: {matched_header}")
            else:
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
    def _detect_semantic_intent(
        self, 
        text: str
    ) -> Tuple[SemanticRole, List[CoverageEffect], List[ExclusionEffect]]:
        """Detect semantic role and specific effects from endorsement text."""
        matched_role = SemanticRole.UNKNOWN
        cov_effects = []
        excl_effects = []
        # Detect Coverage Effects
        for effect, patterns in self.COVERAGE_EFFECT_PATTERNS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                cov_effects.append(effect)
        # Detect Exclusion Effects
        for effect, patterns in self.EXCLUSION_EFFECT_PATTERNS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                excl_effects.append(effect)
        # Apply structural exclusion weighting: if structural exclusion patterns match,
        # it strongly suggests EXCLUSION_MODIFIER even if ambiguous
        has_structural_exclusion = any(re.search(p, text, re.IGNORECASE) for p in self.STRUCTURAL_EXCLUSION_PATTERNS)
        
        # Determine Role based on effects or direct patterns
        if cov_effects and excl_effects:
            # Rule 1: Exclusion carve-backs override coverage signals for role
            # If we have "Exclusion X does not apply", it's primarily an exclusion modifier
            if any(re.search(p, text, re.IGNORECASE) for p in [
                r"exclusion\s+[a-z0-9\.\(\)]+\s+does\s+not\s+apply",
                r"does\s+not\s+apply\s+to\s+one\s+or\s+more"
            ]):
                matched_role = SemanticRole.EXCLUSION_MODIFIER
            else:
                matched_role = SemanticRole.BOTH
        elif cov_effects:
            # Rule 2: Section reference > keyword
            # If we have structural exclusions and coverage effects, it might be BOTH
            # but structural exclusion is a very strong signal.
            if has_structural_exclusion:
                # If "does not apply" carve-back is present, it's often an exclusion modifier
                if any(re.search(p, text, re.IGNORECASE) for p in [
                    r"exclusion\s+[a-z0-9\.\(\)]+\s+does\s+not\s+apply",
                    r"does\s+not\s+apply\s+to\s+one\s+or\s+more"
                ]):
                    matched_role = SemanticRole.EXCLUSION_MODIFIER
                else:
                    matched_role = SemanticRole.BOTH
            else:
                matched_role = SemanticRole.COVERAGE_MODIFIER
        elif excl_effects or has_structural_exclusion:
            matched_role = SemanticRole.EXCLUSION_MODIFIER
        else:
            # Try direct role patterns if no specific effects found
            for role, patterns in self.SEMANTIC_ROLE_PATTERNS.items():
                if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                    matched_role = role
                    break
        return matched_role, cov_effects, excl_effects
    def _has_section_reference(self, text: str) -> bool:
        """Check if text contains section references that boost semantic confidence.
        
        Section references (SECTION II, Coverage A, Exclusion B.1) indicate the endorsement
        is modifying specific policy sections, which is a strong semantic signal.
        """
        return any(re.search(p, text, re.IGNORECASE) for p in self.SECTION_REFERENCE_PATTERNS)