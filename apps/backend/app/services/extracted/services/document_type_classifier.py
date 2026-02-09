"""Document Type Classifier - identifies base forms vs endorsements.

This service analyzes document text to classify insurance documents as:
- Base forms (CA 00 01, CG 00 01, etc.)
- Endorsement packages
- Certificates
- Schedules
- Unknown

Classification is based on pattern matching against known ISO form identifiers,
structural markers, and content analysis.
"""

import re
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from app.schemas.product.synthesis_models import (
    DocumentCategory,
    DocumentTypeResult,
    BaseFormType,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# ISO base form patterns - maps form ID to identifying text patterns
BASE_FORM_PATTERNS = {
    "CA 00 01": [
        r"BUSINESS\s+AUTO\s+COVERAGE\s+FORM",
        r"CA\s*00\s*01",
        r"COMMERCIAL\s+AUTO\s+COVERAGE\s+FORM",
    ],
    "CG 00 01": [
        r"COMMERCIAL\s+GENERAL\s+LIABILITY\s+COVERAGE\s+FORM",
        r"CG\s*00\s*01",
    ],
    "CP 00 10": [
        r"BUILDING\s+AND\s+PERSONAL\s+PROPERTY\s+COVERAGE\s+FORM",
        r"CP\s*00\s*10",
    ],
    "WC 00 00": [
        r"WORKERS\s+COMPENSATION\s+AND\s+EMPLOYERS\s+LIABILITY",
        r"WC\s*00\s*00",
    ],
    "CP 00 30": [
        r"BUSINESS\s+INCOME.*COVERAGE\s+FORM",
        r"CP\s*00\s*30",
    ],
}

# Human-readable names for base forms
FORM_NAMES = {
    "CA 00 01": "Business Auto Coverage Form",
    "CG 00 01": "Commercial General Liability Coverage Form",
    "CP 00 10": "Building and Personal Property Coverage Form",
    "WC 00 00": "Workers Compensation and Employers Liability",
    "CP 00 30": "Business Income Coverage Form",
}

# Endorsement identification patterns
ENDORSEMENT_PATTERNS = [
    r"THIS\s+ENDORSEMENT\s+CHANGES\s+THE\s+POLICY",
    r"This\s+endorsement\s+modifies\s+insurance",
    r"ENDORSEMENT\s+(?:NO\.|NUMBER|#)?\s*(?:CA|CG|IL|WC|CP|IM)\s*\d+",
    r"(?:CA|CG|IL|WC|CP|IM)\s*\d{2}\s*\d{2}",  # Form numbers like CA 04 44
    r"POLICY\s+CHANGE\s+ENDORSEMENT",
    r"SCHEDULE\s+OF\s+ENDORSEMENTS",
]

# Certificate identification patterns
CERTIFICATE_PATTERNS = [
    r"CERTIFICATE\s+OF\s+(?:LIABILITY\s+)?INSURANCE",
    r"ACORD\s+25",
    r"CERTIFICATE\s+HOLDER",
    r"THIS\s+CERTIFICATE\s+IS\s+ISSUED\s+AS\s+A\s+MATTER\s+OF\s+INFORMATION",
]

# Declarations page patterns
DECLARATIONS_PATTERNS = [
    r"DECLARATIONS\s+PAGE",
    r"POLICY\s+DECLARATIONS",
    r"COMMERCIAL\s+(?:AUTO|GENERAL\s+LIABILITY)\s+DECLARATIONS",
    r"ITEM\s+1\.\s+NAMED\s+INSURED",
    r"POLICY\s+PERIOD\s*:",
]

# Schedule patterns
SCHEDULE_PATTERNS = [
    r"SCHEDULE\s+OF\s+(?:FORMS|COVERAGES|LOCATIONS)",
    r"FORMS\s+AND\s+ENDORSEMENTS\s+SCHEDULE",
    r"COVERAGE\s+SCHEDULE",
]

# Form edition date pattern (e.g., "10 13" for October 2013)
EDITION_DATE_PATTERN = r"(\d{2})\s*(\d{2})(?:\s*$|\s+\()"


class DocumentTypeClassifier:
    """Classifies insurance documents as base forms vs endorsements.

    This service uses pattern matching and structural analysis to determine
    the type of insurance document. It identifies:
    - ISO base forms (CA 00 01, CG 00 01, etc.)
    - Endorsement packages
    - Certificates of insurance
    - Declaration pages
    - Schedules

    Attributes:
        logger: Logger instance for the classifier.
    """

    def __init__(self):
        """Initialize the document type classifier."""
        self.logger = LOGGER

    def classify(self, document_text: str) -> DocumentTypeResult:
        """Classify document type from text content.

        Analyzes the document text to determine its category and extract
        relevant metadata like form IDs and endorsement lists.

        Args:
            document_text: The full text content of the document.

        Returns:
            DocumentTypeResult with classification details.
        """
        if not document_text or not document_text.strip():
            return DocumentTypeResult(
                category=DocumentCategory.UNKNOWN,
                confidence=0.0,
            )

        # Normalize text for pattern matching
        normalized_text = self._normalize_text(document_text)
        detected_patterns = []

        # Check for base form first (highest priority for standard form detection)
        base_form_result = self._detect_base_form(normalized_text)
        if base_form_result:
            form_id, patterns = base_form_result
            detected_patterns.extend(patterns)

            # Check if this is a true base form or just references to one
            if self._is_primary_base_form(normalized_text, form_id):
                edition_date = self._extract_edition_date(normalized_text, form_id)

                self.logger.info(
                    f"Classified document as base form: {form_id}",
                    extra={
                        "form_id": form_id,
                        "edition_date": edition_date,
                        "patterns": patterns,
                    }
                )

                return DocumentTypeResult(
                    category=DocumentCategory.BASE_FORM,
                    form_id=form_id,
                    form_name=FORM_NAMES.get(form_id),
                    form_edition_date=edition_date,
                    confidence=0.95,
                    detected_patterns=detected_patterns,
                )

        # Check for endorsement package
        endorsement_result = self._detect_endorsements(normalized_text)
        if endorsement_result:
            endorsement_list, patterns = endorsement_result
            detected_patterns.extend(patterns)

            # If we found endorsements, check if this is primarily an endorsement package
            if len(endorsement_list) > 0 or self._is_endorsement_document(normalized_text):
                self.logger.info(
                    f"Classified document as endorsement package",
                    extra={
                        "endorsement_count": len(endorsement_list),
                        "endorsements": endorsement_list[:5],  # First 5
                    }
                )

                return DocumentTypeResult(
                    category=DocumentCategory.ENDORSEMENT_PACKAGE,
                    endorsement_list=endorsement_list if endorsement_list else None,
                    confidence=0.90,
                    detected_patterns=detected_patterns,
                )

        # Check for certificate
        certificate_patterns = self._detect_patterns(normalized_text, CERTIFICATE_PATTERNS)
        if certificate_patterns:
            detected_patterns.extend(certificate_patterns)
            self.logger.info("Classified document as certificate")

            return DocumentTypeResult(
                category=DocumentCategory.CERTIFICATE,
                confidence=0.90,
                detected_patterns=detected_patterns,
            )

        # Check for declarations
        declarations_patterns = self._detect_patterns(normalized_text, DECLARATIONS_PATTERNS)
        if declarations_patterns:
            detected_patterns.extend(declarations_patterns)
            self.logger.info("Classified document as declarations")

            return DocumentTypeResult(
                category=DocumentCategory.DECLARATIONS,
                confidence=0.85,
                detected_patterns=detected_patterns,
            )

        # Check for schedule
        schedule_patterns = self._detect_patterns(normalized_text, SCHEDULE_PATTERNS)
        if schedule_patterns:
            detected_patterns.extend(schedule_patterns)
            self.logger.info("Classified document as schedule")

            return DocumentTypeResult(
                category=DocumentCategory.SCHEDULE,
                confidence=0.80,
                detected_patterns=detected_patterns,
            )

        # If we detected base form patterns but not as primary, might be mixed document
        if base_form_result:
            form_id, _ = base_form_result
            self.logger.info(
                f"Document references base form {form_id} but classified as unknown",
                extra={"detected_patterns": detected_patterns}
            )

        return DocumentTypeResult(
            category=DocumentCategory.UNKNOWN,
            confidence=0.5 if detected_patterns else 0.3,
            detected_patterns=detected_patterns if detected_patterns else None,
        )

    def classify_multiple(
        self,
        document_texts: List[str]
    ) -> List[DocumentTypeResult]:
        """Classify multiple documents.

        Args:
            document_texts: List of document text contents.

        Returns:
            List of DocumentTypeResult for each document.
        """
        return [self.classify(text) for text in document_texts]

    def extract_form_references(self, document_text: str) -> List[str]:
        """Extract all form references from document text.

        Finds all ISO form numbers mentioned in the document, useful for
        understanding what forms a policy package references.

        Args:
            document_text: The document text to analyze.

        Returns:
            List of unique form IDs found (e.g., ['CA 00 01', 'CA 04 44']).
        """
        normalized_text = self._normalize_text(document_text)
        form_refs = set()

        # Pattern for ISO form numbers
        form_pattern = r"((?:CA|CG|IL|WC|CP|IM)\s*\d{2}\s*\d{2})"
        matches = re.findall(form_pattern, normalized_text, re.IGNORECASE)

        for match in matches:
            # Normalize the form number
            normalized = self._normalize_form_id(match)
            if normalized:
                form_refs.add(normalized)

        return sorted(list(form_refs))

    def _normalize_text(self, text: str) -> str:
        """Normalize text for pattern matching.

        Args:
            text: Raw text to normalize.

        Returns:
            Normalized text with consistent whitespace.
        """
        # Replace multiple whitespace with single space
        normalized = re.sub(r"\s+", " ", text)
        return normalized.upper()

    def _normalize_form_id(self, form_id: str) -> Optional[str]:
        """Normalize a form ID to standard format.

        Args:
            form_id: Raw form ID (e.g., "CA0001", "CA 00 01").

        Returns:
            Normalized form ID (e.g., "CA 00 01") or None if invalid.
        """
        # Remove all whitespace
        cleaned = re.sub(r"\s+", "", form_id.upper())

        # Match pattern like CA0001
        match = re.match(r"([A-Z]{2})(\d{2})(\d{2})", cleaned)
        if match:
            return f"{match.group(1)} {match.group(2)} {match.group(3)}"

        return None

    def _detect_base_form(
        self,
        normalized_text: str
    ) -> Optional[Tuple[str, List[str]]]:
        """Detect if document is a base form.

        Args:
            normalized_text: Normalized document text.

        Returns:
            Tuple of (form_id, matched_patterns) or None if not a base form.
        """
        for form_id, patterns in BASE_FORM_PATTERNS.items():
            matched_patterns = []
            for pattern in patterns:
                if re.search(pattern, normalized_text, re.IGNORECASE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                return (form_id, matched_patterns)

        return None

    def _is_primary_base_form(self, normalized_text: str, form_id: str) -> bool:
        """Determine if document is primarily a base form vs just referencing one.

        A document is considered a primary base form if it contains:
        - The form title prominently
        - Multiple sections (SECTION I, SECTION II, etc.)
        - Coverage grant language ("We will pay...")

        Args:
            normalized_text: Normalized document text.
            form_id: The detected form ID.

        Returns:
            True if this appears to be the actual base form document.
        """
        # Check for section markers typical of base forms
        section_markers = re.findall(
            r"SECTION\s+(?:I|II|III|IV|V|ONE|TWO|THREE|FOUR|FIVE)",
            normalized_text
        )

        # Check for coverage grant language
        has_coverage_grant = bool(re.search(
            r"WE\s+WILL\s+PAY|COVERAGE\s+IS\s+PROVIDED|WE\s+AGREE\s+TO",
            normalized_text
        ))

        # Check for exclusions section (typical of base forms)
        has_exclusions_section = bool(re.search(
            r"EXCLUSIONS|THIS\s+INSURANCE\s+DOES\s+NOT\s+APPLY",
            normalized_text
        ))

        # Check that it's NOT primarily an endorsement
        endorsement_indicators = len(re.findall(
            r"THIS\s+ENDORSEMENT\s+CHANGES",
            normalized_text
        ))

        # Scoring logic
        base_form_indicators = len(section_markers) + (2 if has_coverage_grant else 0) + (1 if has_exclusions_section else 0)

        # If multiple endorsement changes and fewer base form indicators, not primary
        if endorsement_indicators > 1 and base_form_indicators < 3:
            return False

        # Need substantial base form content
        return base_form_indicators >= 2

    def _detect_endorsements(
        self,
        normalized_text: str
    ) -> Optional[Tuple[List[str], List[str]]]:
        """Detect endorsement patterns and extract endorsement numbers.

        Args:
            normalized_text: Normalized document text.

        Returns:
            Tuple of (endorsement_list, matched_patterns) or None.
        """
        matched_patterns = self._detect_patterns(normalized_text, ENDORSEMENT_PATTERNS)

        if not matched_patterns:
            return None

        # Extract endorsement numbers
        endorsement_numbers = []

        # Pattern for endorsement form numbers (e.g., CA 04 44, IL 00 21)
        form_pattern = r"((?:CA|CG|IL|WC|CP|IM)\s*\d{2}\s*\d{2})"
        form_matches = re.findall(form_pattern, normalized_text)

        for match in form_matches:
            normalized = self._normalize_form_id(match)
            if normalized and normalized not in endorsement_numbers:
                # Exclude known base forms from endorsement list
                if normalized not in BASE_FORM_PATTERNS:
                    endorsement_numbers.append(normalized)

        return (endorsement_numbers, matched_patterns)

    def _is_endorsement_document(self, normalized_text: str) -> bool:
        """Check if document is primarily an endorsement document.

        Args:
            normalized_text: Normalized document text.

        Returns:
            True if document appears to be an endorsement.
        """
        # Count endorsement change markers
        change_markers = len(re.findall(
            r"THIS\s+ENDORSEMENT\s+CHANGES|THIS\s+ENDORSEMENT\s+MODIFIES",
            normalized_text
        ))

        return change_markers >= 1

    def _detect_patterns(
        self,
        normalized_text: str,
        patterns: List[str]
    ) -> List[str]:
        """Detect which patterns match in text.

        Args:
            normalized_text: Normalized document text.
            patterns: List of regex patterns to check.

        Returns:
            List of patterns that matched.
        """
        matched = []
        for pattern in patterns:
            if re.search(pattern, normalized_text, re.IGNORECASE):
                matched.append(pattern)
        return matched

    def _extract_edition_date(
        self,
        normalized_text: str,
        form_id: str
    ) -> Optional[str]:
        """Extract form edition date from document.

        Args:
            normalized_text: Normalized document text.
            form_id: The form ID to look for edition date near.

        Returns:
            Edition date string (e.g., "10 13") or None.
        """
        # Look for pattern like "CA 00 01 10 13" or "CA 00 01 (10 13)"
        form_pattern = form_id.replace(" ", r"\s*")
        edition_pattern = rf"{form_pattern}\s*(?:\()?(\d{{2}})\s*(\d{{2}})"

        match = re.search(edition_pattern, normalized_text)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        return None

    def get_form_name(self, form_id: str) -> Optional[str]:
        """Get human-readable name for a form ID.

        Args:
            form_id: ISO form ID (e.g., "CA 00 01").

        Returns:
            Human-readable form name or None if unknown.
        """
        return FORM_NAMES.get(form_id)

    def is_base_form_id(self, form_id: str) -> bool:
        """Check if a form ID is a known base form.

        Args:
            form_id: ISO form ID to check.

        Returns:
            True if form ID is a known base form.
        """
        normalized = self._normalize_form_id(form_id)
        return normalized in BASE_FORM_PATTERNS if normalized else False
