"""OCR normalization service for insurance document text cleaning.

This service implements comprehensive text normalization for OCR-extracted
insurance documents using a hybrid LLM + code approach:
- Stage 1: LLM-based structural cleanup (tables, hyphenation, OCR artifacts)
- Stage 2: Deterministic field normalization (dates, amounts, policy numbers)

It also maintains the legacy rule-based approach for backward compatibility.
"""

from typing import Dict, List, Optional, Tuple, Any

from app.services.normalization.llm_normalizer import LLMNormalizer
from app.services.normalization.semantic_normalizer import SemanticNormalizer
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationService:
    """Service for normalizing OCR-extracted text from insurance documents.
    
    This service supports two normalization approaches:
    
    **Hybrid Approach (Recommended)**:
    1. LLM-based structural cleanup (tables, hyphenation, OCR artifacts)
    2. Deterministic field normalization (dates, amounts, policy numbers)
    
    **Legacy Rule-Based Approach**:
    1. Removes garbage characters and noise
    2. Fixes structural issues (hyphenation, line breaks)
    3. Standardizes insurance-specific terminology
    4. Removes headers, footers, and page numbers
    5. Normalizes financial amounts and dates
    
    The hybrid approach is more robust and maintainable, offloading complex
    structural cleanup to the LLM while keeping deterministic operations in code.
    
    Attributes:
        llm_normalizer: LLM-based text normalizer (optional)
        semantic_normalizer: Semantic field normalizer
        use_hybrid: Whether to use hybrid approach (default: True)
        insurance_term_fixes: Dictionary mapping common OCR errors to correct terms
        header_patterns: Common header patterns to remove
        footer_patterns: Common footer patterns to remove
    """
    
    # Common OCR misreads of insurance terms
    INSURANCE_TERM_FIXES = {
        # Policy variations
        r'\bPoIicy\b': 'Policy',
        r'\bPo1icy\b': 'Policy',
        r'\bPoIicies\b': 'Policies',
        r'\bPoI\b': 'Policy',
        
        # Claim variations
        r'\bC1aim\b': 'Claim',
        r'\bC\|aim\b': 'Claim',
        r'\bCIaim\b': 'Claim',
        r'\bC1aims\b': 'Claims',
        
        # Premium variations
        r'\bPremIum\b': 'Premium',
        r'\bPremlum\b': 'Premium',
        r'\bPrem1um\b': 'Premium',
        
        # Endorsement variations
        r'\bEndorse\s*ment\b': 'Endorsement',
        r'\bEndorse-\s*ment\b': 'Endorsement',
        
        # Coverage variations
        r'\bCoverage\s+A\b': 'Coverage A',
        r'\bCoverage-A\b': 'Coverage A',
        
        # Common insurance terms
        r'\bInsur-\s*ance\b': 'Insurance',
        r'\bInsur\s*ance\b': 'Insurance',
        r'\bDeduct-\s*ible\b': 'Deductible',
        r'\bDeductib1e\b': 'Deductible',
    }
    
    # Common header patterns in insurance documents
    HEADER_PATTERNS = [
        r'Policy\s+Declarations?',
        r'Commercial\s+Package\s+Policy',
        r'Liberty\s+Mutual\s+Insurance\s+Company',
        r'State\s+Farm\s+Insurance',
        r'Allstate\s+Insurance\s+Company',
        r'Progressive\s+Insurance',
        r'GEICO\s+Insurance',
        r'Farmers\s+Insurance',
        r'Certificate\s+of\s+Insurance',
        r'ACORD\s+\d+',
        r'Schedule\s+of\s+Values',
    ]
    
    # Common footer patterns
    FOOTER_PATTERNS = [
        r'Page\s+\d+\s+of\s+\d+',
        r'\d+\s*/\s*\d+',
        r'Confidential',
        r'Printed\s+on:?\s*\d{4}-\d{2}-\d{2}',
        r'Printed\s+on:?\s*\d{1,2}/\d{1,2}/\d{2,4}',
        r'Generated\s+on:?\s*\d{4}-\d{2}-\d{2}',
    ]
    
    def __init__(
        self,
        openrouter_api_key: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        use_hybrid: bool = True,
    ):
        """Initialize OCR normalization service.
        
        Args:
            api_key: Mistral API key for LLM normalization (required if use_hybrid=True)
            use_hybrid: Whether to use hybrid LLM + code approach (default: True)
            llm_model: LLM model to use for normalization
        """
        self.use_hybrid = use_hybrid
        self.semantic_normalizer = SemanticNormalizer()
        
        # Initialize LLM normalizer if using hybrid approach
        self.llm_normalizer = None
        if use_hybrid:
            if not openrouter_api_key:
                LOGGER.warning(
                    "Hybrid normalization enabled but no API key provided. "
                    "Falling back to rule-based normalization."
                )
                self.use_hybrid = False
            else:
                self.llm_normalizer = LLMNormalizer(
                    openrouter_api_key=openrouter_api_key,
                    openrouter_api_url=openrouter_api_url,
                    openrouter_model=openrouter_model,
                )
        
        LOGGER.info(
            "Initialized OCR normalization service",
            extra={
                "use_hybrid": self.use_hybrid,
                "llm_model": openrouter_model if self.use_hybrid else None,
            }
        )
    
    async def normalize_text(self, raw_text: str) -> str:
        """Execute complete normalization pipeline on OCR text.
        
        This is the main entry point for text normalization. It automatically
        selects between hybrid and rule-based approaches based on configuration.
        
        Args:
            raw_text: Raw OCR-extracted text to normalize
            
        Returns:
            str: Normalized, clean text ready for downstream processing
            
        Example:
            >>> service = OCRNormalizationService(api_key="...")
            >>> raw = "PoIicy Number: 12345\\nPage 1 of 5\\nPremIum: $1,234.00"
            >>> clean = await service.normalize_text(raw)
            >>> print(clean)
            Policy Number: 12345
            Premium: 1234.00
        """
        if not raw_text or not raw_text.strip():
            LOGGER.warning("Empty text provided for normalization")
            return ""
        
        if self.use_hybrid and self.llm_normalizer:
            return await self._normalize_text_hybrid(raw_text)
        else:
            return self._normalize_text_legacy(raw_text)
    
    async def _normalize_text_hybrid(self, raw_text: str) -> str:
        """Execute hybrid LLM + code normalization pipeline.
        
        Stage 1: LLM structural cleanup
        Stage 2: Deterministic field normalization
        
        Args:
            raw_text: Raw OCR-extracted text
            
        Returns:
            str: Normalized text
        """
        LOGGER.info(
            "Starting hybrid normalization",
            extra={"original_length": len(raw_text)}
        )
        
        # Stage 1: LLM structural cleanup
        llm_normalized = await self.llm_normalizer.normalize(raw_text)
        
        # Stage 2: Semantic field normalization
        result = self.semantic_normalizer.normalize_text_with_fields(llm_normalized)
        final_text = result["normalized_text"]
        
        LOGGER.info(
            "Hybrid normalization completed",
            extra={
                "original_length": len(raw_text),
                "llm_normalized_length": len(llm_normalized),
                "final_length": len(final_text),
                "dates_extracted": len(result["extracted_fields"]["dates"]),
                "amounts_extracted": len(result["extracted_fields"]["amounts"]),
            }
        )
        
        return final_text
    
    def _normalize_text_legacy(self, raw_text: str) -> str:
        """Execute legacy rule-based normalization pipeline.
        
        This is the original normalization approach, kept for backward compatibility.
        
        Args:
            raw_text: Raw OCR-extracted text to normalize
            
        Returns:
            str: Normalized, clean text ready for downstream processing
        """
        LOGGER.info(
            "Starting legacy normalization",
            extra={"original_length": len(raw_text)}
        )
        
        # Step A: Basic text cleaning
        text = self._remove_garbage_characters(raw_text)
        text = self._normalize_whitespace(text)
        text = self._remove_page_numbers(text)
        text = self._remove_headers(text)
        text = self._remove_footers(text)
        text = self._fix_hyphenation(text)
        
        # Step B: Structural normalization
        text = self._fix_broken_lines(text)
        text = self._normalize_lists(text)
        text = self._normalize_newlines(text)
        
        # Step C: Insurance-specific normalization
        text = self._fix_insurance_terms(text)
        text = self._normalize_amounts(text)
        text = self._normalize_dates(text)
        text = self._normalize_policy_number(text)
        
        # Final cleanup
        text = self._final_cleanup(text)
        
        LOGGER.info(
            "Legacy normalization completed",
            extra={
                "original_length": len(raw_text),
                "normalized_length": len(text),
                "reduction_percent": round((1 - len(text) / len(raw_text)) * 100, 2)
            }
        )
        
        return text
    
    def _remove_garbage_characters(self, text: str) -> str:
        """Remove non-printable and OCR artifact characters.
        
        Removes characters that are not standard ASCII printable characters,
        while preserving newlines which are important for structure.
        
        Args:
            text: Text containing garbage characters
            
        Returns:
            str: Text with garbage characters removed
        """
        # Keep only ASCII printable characters and newlines
        # ASCII printable range: 0x20-0x7E, plus \n (0x0A)
        cleaned = re.sub(r'[^\x20-\x7E\n]', '', text)
        
        LOGGER.debug("Removed garbage characters")
        return cleaned
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters.
        
        Converts tabs to spaces, collapses multiple spaces into single spaces,
        and limits consecutive newlines to a maximum of 2.
        
        Args:
            text: Text with inconsistent whitespace
            
        Returns:
            str: Text with normalized whitespace
        """
        # Convert tabs to spaces
        text = text.replace('\t', ' ')
        
        # Collapse multiple spaces into single space
        text = re.sub(r'[ ]+', ' ', text)
        
        # Limit consecutive newlines to maximum of 2
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        LOGGER.debug("Normalized whitespace")
        return text
    
    def _remove_page_numbers(self, text: str) -> str:
        """Remove page numbers and pagination markers.
        
        Args:
            text: Text containing page numbers
            
        Returns:
            str: Text with page numbers removed
        """
        # Remove "Page X of Y" patterns
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
        
        # Remove "X/Y" patterns (only if on their own line)
        text = re.sub(r'^\s*\d+\s*/\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Remove standalone numbers on their own lines (likely page numbers)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
        
        LOGGER.debug("Removed page numbers")
        return text
    
    def _remove_headers(self, text: str) -> str:
        """Remove common insurance document headers.
        
        Args:
            text: Text containing headers
            
        Returns:
            str: Text with headers removed
        """
        for pattern in self.HEADER_PATTERNS:
            # Remove headers that appear at the beginning of lines
            text = re.sub(
                rf'^\s*{pattern}\s*$',
                '',
                text,
                flags=re.MULTILINE | re.IGNORECASE
            )
        
        LOGGER.debug("Removed headers")
        return text
    
    def _remove_footers(self, text: str) -> str:
        """Remove common footer patterns.
        
        Args:
            text: Text containing footers
            
        Returns:
            str: Text with footers removed
        """
        for pattern in self.FOOTER_PATTERNS:
            text = re.sub(
                pattern,
                '',
                text,
                flags=re.IGNORECASE
            )
        
        LOGGER.debug("Removed footers")
        return text
    
    def _fix_hyphenation(self, text: str) -> str:
        """Fix broken words caused by OCR hyphenation.
        
        OCR often produces "Poli- cy" or "Commer- cial" for words split
        across lines. This method rejoins these words.
        
        Args:
            text: Text with hyphenation issues
            
        Returns:
            str: Text with hyphenation fixed
        """
        # Fix hyphenated words split across lines
        # Pattern: word-\n word or word- \n word
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
        
        # Fix hyphenated words with space before next part
        # Pattern: word- word
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
        
        LOGGER.debug("Fixed hyphenation")
        return text
    
    def _fix_broken_lines(self, text: str) -> str:
        """Fix sentences broken across multiple lines.
        
        Insurance documents often have sentences split across lines.
        This method merges lines that don't end with punctuation
        and are followed by lowercase text.
        
        Args:
            text: Text with broken lines
            
        Returns:
            str: Text with lines merged appropriately
        """
        lines = text.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            current_line = lines[i].strip()
            
            # Check if we should merge with next line
            if (i < len(lines) - 1 and
                current_line and
                not current_line[-1] in '.!?:' and
                lines[i + 1].strip() and
                lines[i + 1].strip()[0].islower()):
                
                # Merge with next line
                next_line = lines[i + 1].strip()
                fixed_lines.append(f"{current_line} {next_line}")
                i += 2
            else:
                fixed_lines.append(current_line)
                i += 1
        
        LOGGER.debug("Fixed broken lines")
        return '\n'.join(fixed_lines)
    
    def _normalize_lists(self, text: str) -> str:
        """Normalize inconsistent list formatting.
        
        OCR often produces inconsistent list bullets and formatting.
        This method standardizes list formatting.
        
        Args:
            text: Text with inconsistent lists
            
        Returns:
            str: Text with normalized lists
        """
        # Normalize various bullet characters to standard bullet
        bullet_chars = ['•', '◦', '▪', '▫', '‣', '⁃', '-', '*']
        for char in bullet_chars:
            text = re.sub(
                rf'^\s*{re.escape(char)}\s*',
                '• ',
                text,
                flags=re.MULTILINE
            )
        
        LOGGER.debug("Normalized lists")
        return text
    
    def _normalize_newlines(self, text: str) -> str:
        """Ensure consistent paragraph separation.
        
        Args:
            text: Text with inconsistent newlines
            
        Returns:
            str: Text with normalized paragraph separation
        """
        # Remove excessive blank lines (already limited to 2 by whitespace normalization)
        # Ensure single blank line between paragraphs
        lines = text.split('\n')
        normalized = []
        prev_empty = False
        
        for line in lines:
            is_empty = not line.strip()
            
            if is_empty:
                if not prev_empty:
                    normalized.append('')
                prev_empty = True
            else:
                normalized.append(line)
                prev_empty = False
        
        LOGGER.debug("Normalized newlines")
        return '\n'.join(normalized)
    
    def _fix_insurance_terms(self, text: str) -> str:
        """Fix commonly misread insurance terminology.
        
        Args:
            text: Text with misread insurance terms
            
        Returns:
            str: Text with corrected insurance terms
        """
        for pattern, replacement in self.INSURANCE_TERM_FIXES.items():
            text = re.sub(pattern, replacement, text)
        
        LOGGER.debug("Fixed insurance terms")
        return text
    
    def _normalize_amounts(self, text: str) -> str:
        """Normalize financial amounts for consistency.
        
        This method standardizes currency formatting by removing
        currency symbols and thousand separators while preserving
        the numeric values and decimal points.
        
        Args:
            text: Text containing financial amounts
            
        Returns:
            str: Text with normalized amounts
        """
        # Pattern to match currency amounts
        # Matches: $1,234.56 or ₹25,000/- or $1,234
        currency_pattern = r'([$₹£€])?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(/-)?' 
        
        def normalize_amount(match):
            amount = match.group(2)
            # Remove commas from amount
            normalized = amount.replace(',', '')
            return normalized
        
        text = re.sub(currency_pattern, normalize_amount, text)
        
        LOGGER.debug("Normalized amounts")
        return text
    
    def _normalize_dates(self, text: str) -> str:
        """Normalize date formats to ISO format (YYYY-MM-DD).
        
        This method attempts to standardize various date formats
        found in insurance documents to a consistent ISO format.
        
        Args:
            text: Text containing various date formats
            
        Returns:
            str: Text with normalized dates
        """
        # Pattern 1: MM/DD/YYYY or MM-DD-YYYY
        text = re.sub(
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',
            r'\3-\1-\2',
            text
        )
        
        # Pattern 2: DD/MM/YY or MM/DD/YY (ambiguous, assume MM/DD)
        text = re.sub(
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b',
            r'20\3-\1-\2',
            text
        )
        
        # Fix OCR errors in dates: O1 -> 01, 0l -> 01, etc.
        text = re.sub(r'\bO(\d)', r'0\1', text)
        text = re.sub(r'\b0l\b', '01', text)
        
        LOGGER.debug("Normalized dates")
        return text
    
    def _final_cleanup(self, text: str) -> str:
        """Perform final cleanup operations.
        
        Args:
            text: Text after all normalization steps
            
        Returns:
            str: Final cleaned text
        """
        # Remove any remaining multiple spaces
        text = re.sub(r' {2,}', ' ', text)
        
        # Remove spaces at the beginning and end of lines
        text = '\n'.join(line.strip() for line in text.split('\n'))
        
        # Remove leading/trailing whitespace from entire text
        text = text.strip()
        
        # Ensure no more than one blank line between paragraphs
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        LOGGER.debug("Completed final cleanup")
        return text
    
    def normalize_page_text(
        self,
        page_text: str,
        page_number: int
    ) -> Dict[str, any]:
        """Normalize text from a single page.
        
        This method is useful for page-level processing and debugging.
        
        Args:
            page_text: Raw text from a single page
            page_number: Page number for logging
            
        Returns:
            dict: Dictionary containing normalized text and metadata
        """
        LOGGER.debug(
            "Normalizing page text",
            extra={"page_number": page_number}
        )
        
        normalized_text = self.normalize_text(page_text)
        
        return {
            "page_number": page_number,
            "original_length": len(page_text),
            "normalized_length": len(normalized_text),
            "normalized_text": normalized_text,
        }
    
    def detect_document_sections(self, text: str) -> Dict[str, List[str]]:
        """Detect common insurance document sections.
        
        This method identifies key sections in insurance documents
        which can be useful for downstream classification and extraction.
        
        Args:
            text: Normalized document text
            
        Returns:
            dict: Dictionary mapping section names to line numbers where found
        """
        sections = {
            "declarations": [],
            "endorsements": [],
            "exclusions": [],
            "insuring_agreement": [],
            "schedule_of_values": [],
            "premium_summary": [],
            "loss_history": [],
            "coverages": [],
        }
        
        section_patterns = {
            "declarations": r'\bdeclarations?\b',
            "endorsements": r'\bendorsements?\b',
            "exclusions": r'\bexclusions?\b',
            "insuring_agreement": r'\binsuring agreement\b',
            "schedule_of_values": r'\bschedule of values\b|\bSOV\b',
            "premium_summary": r'\bpremium summary\b',
            "loss_history": r'\bloss (history|runs?)\b',
            "coverages": r'\bcoverages?\b',
        }
        
        lines = text.split('\n')
        for line_num, line in enumerate(lines, start=1):
            line_lower = line.lower()
            for section_name, pattern in section_patterns.items():
                if re.search(pattern, line_lower):
                    sections[section_name].append(line_num)
        
        detected = {k: v for k, v in sections.items() if v}
        
        if detected:
            LOGGER.info(
                "Detected document sections",
                extra={"sections": list(detected.keys())}
            )
        
        return detected
