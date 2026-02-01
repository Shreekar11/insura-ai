"""Base Form Extractor - extracts standard provisions from ISO base forms.

This service extracts coverages, exclusions, and conditions from standard
insurance policy forms like CA 00 01 (Business Auto), CG 00 01 (CGL), etc.

The extractor uses a combination of:
1. Pattern-based extraction for known form structures
2. LLM-assisted extraction for complex or varied content
3. Standard provision knowledge base for validation
"""

from typing import Dict, List, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.schemas.product.synthesis_models import (
    StandardProvision,
    BaseFormExtractionResult,
    DocumentCategory,
)
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


# Standard exclusions for CA 00 01 Business Auto Coverage Form
# Section II - Liability Coverage, B. Exclusions (13 standard exclusions)
CA_00_01_STANDARD_EXCLUSIONS = [
    {
        "provision_number": "B.1",
        "provision_name": "Expected Or Intended Injury",
        "description": "No coverage for bodily injury or property damage expected or intended from the standpoint of the insured.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.2",
        "provision_name": "Contractual",
        "description": "No coverage for liability assumed under contract or agreement, with specific exceptions for lease agreements and insured contracts.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.3",
        "provision_name": "Workers' Compensation",
        "description": "No coverage for any obligation for which the insured may be held liable under workers' compensation, disability benefits, or similar law.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.4",
        "provision_name": "Employee Indemnification And Employer's Liability",
        "description": "No coverage for bodily injury to an employee of the insured arising out of employment, or for employer's liability for such injury.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.5",
        "provision_name": "Fellow Employee",
        "description": "No coverage for bodily injury to any fellow employee of the insured arising out of the fellow employee's employment.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.6",
        "provision_name": "Care, Custody Or Control",
        "description": "No coverage for property damage to property owned or transported by the insured, or in the insured's care, custody or control.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.7",
        "provision_name": "Handling Of Property",
        "description": "No coverage for bodily injury or property damage resulting from handling of property before or after movement on a covered auto.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.8",
        "provision_name": "Movement Of Property By Mechanical Device",
        "description": "No coverage for bodily injury or property damage resulting from movement of property by mechanical device not attached to the covered auto.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.9",
        "provision_name": "Operations",
        "description": "No coverage for bodily injury or property damage arising out of the operation of mobile equipment.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.10",
        "provision_name": "Completed Operations",
        "description": "No coverage for bodily injury or property damage arising out of your work after it has been completed.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.11",
        "provision_name": "Pollution",
        "description": "No coverage for bodily injury or property damage arising from pollution, with limited exceptions for covered pollution costs.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.12",
        "provision_name": "War",
        "description": "No coverage for bodily injury or property damage arising from war, insurrection, rebellion, or revolution.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
    {
        "provision_number": "B.13",
        "provision_name": "Racing",
        "description": "No coverage for covered autos while used in any professional or organized racing or demolition contest.",
        "form_section": "SECTION II - LIABILITY COVERAGE",
    },
]

# Standard coverages for CA 00 01 Business Auto Coverage Form
CA_00_01_STANDARD_COVERAGES = [
    {
        "provision_number": "II.A",
        "provision_name": "Covered Autos Liability Coverage",
        "description": "Pays all sums the insured legally must pay as damages because of bodily injury or property damage caused by an accident resulting from ownership, maintenance, or use of a covered auto.",
        "form_section": "SECTION II - COVERED AUTOS LIABILITY COVERAGE",
        "sub_provisions": [
            "Bodily Injury Coverage",
            "Property Damage Coverage",
            "Covered Pollution Cost or Expense",
            "Defense and Settlement Duties",
        ],
    },
    {
        "provision_number": "III.A",
        "provision_name": "Physical Damage Coverage - Comprehensive",
        "description": "Covers loss to a covered auto or its equipment from any cause except collision or overturn, or loss from mischief, vandalism, or hitting or being hit by a bird or animal.",
        "form_section": "SECTION III - PHYSICAL DAMAGE COVERAGE",
    },
    {
        "provision_number": "III.B",
        "provision_name": "Physical Damage Coverage - Collision",
        "description": "Covers loss to a covered auto or its equipment caused by collision with another object or by overturn.",
        "form_section": "SECTION III - PHYSICAL DAMAGE COVERAGE",
    },
    {
        "provision_number": "III.C",
        "provision_name": "Physical Damage Coverage - Specified Causes of Loss",
        "description": "Covers loss to a covered auto or its equipment only from fire, lightning, explosion, theft, windstorm, hail, earthquake, flood, mischief, vandalism, or sinking of a vessel.",
        "form_section": "SECTION III - PHYSICAL DAMAGE COVERAGE",
    },
    {
        "provision_number": "III.D",
        "provision_name": "Towing",
        "description": "Covers towing and labor costs incurred each time a covered auto is disabled, subject to specified limit.",
        "form_section": "SECTION III - PHYSICAL DAMAGE COVERAGE",
    },
    {
        "provision_number": "III.E",
        "provision_name": "Glass Breakage - Hitting A Bird Or Animal - Falling Objects Or Missiles",
        "description": "Loss caused by glass breakage, hitting a bird or animal, or falling objects or missiles may be treated as comprehensive coverage or collision coverage depending on deductible preferences.",
        "form_section": "SECTION III - PHYSICAL DAMAGE COVERAGE",
    },
]

# Standard conditions for CA 00 01
CA_00_01_STANDARD_CONDITIONS = [
    {
        "provision_number": "IV.A",
        "provision_name": "Loss Conditions",
        "description": "Procedures and requirements in the event of loss including appraisal, duties after accident or loss, legal action requirements, loss payment provisions, and transfer of rights.",
        "form_section": "SECTION IV - CONDITIONS",
    },
    {
        "provision_number": "IV.B",
        "provision_name": "General Conditions",
        "description": "General policy conditions including bankruptcy provisions, concealment or fraud, liberalization, other insurance, premium audit, policy period and coverage territory, and two or more coverage forms.",
        "form_section": "SECTION IV - CONDITIONS",
    },
]

# Knowledge base for other form types - can be expanded
FORM_KNOWLEDGE_BASE = {
    "CA 00 01": {
        "form_name": "Business Auto Coverage Form",
        "exclusions": CA_00_01_STANDARD_EXCLUSIONS,
        "coverages": CA_00_01_STANDARD_COVERAGES,
        "conditions": CA_00_01_STANDARD_CONDITIONS,
    },
    # Additional forms can be added here
}


# Prompt for LLM-based base form extraction
BASE_FORM_EXTRACTION_PROMPT = """You are an expert insurance policy analyst specializing in ISO standard forms.

Your task is to extract ALL standard coverages, exclusions, and conditions from this base policy form.

IMPORTANT RULES:
1. Extract ONLY provisions explicitly stated in the document
2. Preserve exact section numbers and letters (e.g., "B.1", "Section II.A")
3. Include the verbatim title/name of each provision
4. Provide a concise description of what each provision does
5. Identify the form section (e.g., "SECTION II - LIABILITY COVERAGE")

For BASE FORMS like CA 00 01 (Business Auto), expect:
- SECTION I: Covered Autos
- SECTION II: Liability Coverage (with ~13 standard exclusions)
- SECTION III: Physical Damage Coverage
- SECTION IV: Conditions
- SECTION V: Definitions

OUTPUT FORMAT (strict JSON):
{
  "form_id": "CA 00 01",
  "form_name": "Business Auto Coverage Form",
  "form_edition_date": "10 13",
  "coverages": [
    {
      "provision_number": "II.A",
      "provision_name": "Covered Autos Liability Coverage",
      "description": "Pays damages for bodily injury or property damage from covered auto accidents",
      "form_section": "SECTION II",
      "sub_provisions": ["Defense costs", "Supplementary payments"],
      "verbatim_text": "We will pay all sums..."
    }
  ],
  "exclusions": [
    {
      "provision_number": "B.1",
      "provision_name": "Expected Or Intended Injury",
      "description": "No coverage for intentional acts",
      "form_section": "SECTION II",
      "verbatim_text": "This insurance does not apply to..."
    }
  ],
  "conditions": [
    {
      "provision_number": "IV.A",
      "provision_name": "Loss Conditions",
      "description": "Procedures after a loss",
      "form_section": "SECTION IV"
    }
  ],
  "definitions": [
    {
      "provision_number": "V.1",
      "provision_name": "Auto",
      "description": "Definition of 'auto' as used in this policy",
      "form_section": "SECTION V"
    }
  ],
  "confidence": 0.95
}

Focus especially on EXCLUSIONS as they are critical for coverage analysis.
Extract ALL numbered exclusions (B.1 through B.13 for auto policies).
"""


class BaseFormExtractor(BaseExtractor):
    """Extracts standard provisions from ISO base forms.

    This extractor handles base policy forms like CA 00 01, CG 00 01, etc.
    It combines knowledge base lookups with LLM extraction for comprehensive
    coverage of standard provisions.

    Attributes:
        knowledge_base: Static knowledge of standard form provisions.
        use_llm: Whether to use LLM for extraction vs knowledge base only.
    """

    def __init__(
        self,
        session: AsyncSession,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
        use_llm: bool = True,
    ):
        """Initialize base form extractor.

        Args:
            session: SQLAlchemy async session.
            provider: LLM provider ("gemini" or "openrouter").
            gemini_api_key: Gemini API key.
            gemini_model: Gemini model name.
            openrouter_api_key: OpenRouter API key.
            openrouter_model: OpenRouter model name.
            openrouter_api_url: OpenRouter API URL.
            use_llm: Whether to use LLM for extraction (vs knowledge base only).
        """
        super().__init__(
            session=session,
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
            openrouter_api_url=openrouter_api_url,
        )
        self.use_llm = use_llm
        self.knowledge_base = FORM_KNOWLEDGE_BASE
        self.logger = LOGGER

    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for base forms."""
        return BASE_FORM_EXTRACTION_PROMPT

    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract provisions from base form text.

        Args:
            text: The document text to extract from.
            document_id: Document ID for tracking.
            chunk_id: Optional chunk ID.

        Returns:
            List containing the BaseFormExtractionResult.
        """
        result = await self.extract_base_form(text, document_id)
        return [result.model_dump()]

    async def extract_base_form(
        self,
        document_text: str,
        document_id: Optional[UUID] = None,
        form_id: Optional[str] = None,
    ) -> BaseFormExtractionResult:
        """Extract all provisions from a base form document.

        This method coordinates extraction using both knowledge base and
        LLM extraction, merging results for comprehensive coverage.

        Args:
            document_text: The full document text.
            document_id: Optional document ID for tracking.
            form_id: Optional form ID if already known.

        Returns:
            BaseFormExtractionResult with all extracted provisions.
        """
        # Detect form ID if not provided
        if not form_id:
            form_id = self._detect_form_id(document_text)

        if not form_id:
            self.logger.warning("Could not detect form ID, using LLM extraction only")
            return await self._extract_with_llm(document_text)

        self.logger.info(
            f"Extracting base form provisions for {form_id}",
            extra={"document_id": str(document_id) if document_id else None}
        )

        # Check if we have knowledge base entry for this form
        if form_id in self.knowledge_base:
            kb_result = self._extract_from_knowledge_base(form_id)

            # If LLM extraction is enabled, enhance with document-specific details
            if self.use_llm:
                try:
                    llm_result = await self._extract_with_llm(document_text)
                    return self._merge_results(kb_result, llm_result)
                except Exception as e:
                    self.logger.warning(
                        f"LLM extraction failed, using knowledge base only: {e}"
                    )
                    return kb_result
            return kb_result

        # No knowledge base entry - use LLM extraction
        return await self._extract_with_llm(document_text)

    def extract_standard_exclusions(
        self,
        form_id: str
    ) -> List[StandardProvision]:
        """Extract standard exclusions for a known form type.

        This method provides the canonical list of exclusions for standard
        ISO forms without requiring document text.

        Args:
            form_id: ISO form ID (e.g., "CA 00 01").

        Returns:
            List of StandardProvision for exclusions.
        """
        if form_id not in self.knowledge_base:
            self.logger.warning(f"No knowledge base entry for form {form_id}")
            return []

        form_data = self.knowledge_base[form_id]
        exclusions = []

        for excl in form_data.get("exclusions", []):
            exclusions.append(StandardProvision(
                provision_name=excl["provision_name"],
                provision_type="exclusion",
                provision_number=excl.get("provision_number"),
                source_form=form_id,
                form_section=excl.get("form_section"),
                description=excl.get("description"),
                sub_provisions=excl.get("sub_provisions"),
                confidence=0.95,
            ))

        return exclusions

    def extract_standard_coverages(
        self,
        form_id: str
    ) -> List[StandardProvision]:
        """Extract standard coverages for a known form type.

        Args:
            form_id: ISO form ID (e.g., "CA 00 01").

        Returns:
            List of StandardProvision for coverages.
        """
        if form_id not in self.knowledge_base:
            self.logger.warning(f"No knowledge base entry for form {form_id}")
            return []

        form_data = self.knowledge_base[form_id]
        coverages = []

        for cov in form_data.get("coverages", []):
            coverages.append(StandardProvision(
                provision_name=cov["provision_name"],
                provision_type="coverage",
                provision_number=cov.get("provision_number"),
                source_form=form_id,
                form_section=cov.get("form_section"),
                description=cov.get("description"),
                sub_provisions=cov.get("sub_provisions"),
                confidence=0.95,
            ))

        return coverages

    def _detect_form_id(self, document_text: str) -> Optional[str]:
        """Detect the form ID from document text.

        Args:
            document_text: The document text to analyze.

        Returns:
            Detected form ID or None.
        """
        import re

        # Check for known form patterns
        for form_id in self.knowledge_base.keys():
            pattern = form_id.replace(" ", r"\s*")
            if re.search(pattern, document_text, re.IGNORECASE):
                return form_id

        # Try generic ISO form pattern
        match = re.search(
            r"((?:CA|CG|IL|WC|CP)\s*00\s*\d{2})",
            document_text,
            re.IGNORECASE
        )
        if match:
            # Normalize
            raw = match.group(1)
            cleaned = re.sub(r"\s+", "", raw.upper())
            form_match = re.match(r"([A-Z]{2})(\d{2})(\d{2})", cleaned)
            if form_match:
                return f"{form_match.group(1)} {form_match.group(2)} {form_match.group(3)}"

        return None

    def _extract_from_knowledge_base(
        self,
        form_id: str
    ) -> BaseFormExtractionResult:
        """Extract provisions from knowledge base.

        Args:
            form_id: The form ID to look up.

        Returns:
            BaseFormExtractionResult from knowledge base.
        """
        form_data = self.knowledge_base[form_id]

        coverages = [
            StandardProvision(
                provision_name=cov["provision_name"],
                provision_type="coverage",
                provision_number=cov.get("provision_number"),
                source_form=form_id,
                form_section=cov.get("form_section"),
                description=cov.get("description"),
                sub_provisions=cov.get("sub_provisions"),
                confidence=0.95,
            )
            for cov in form_data.get("coverages", [])
        ]

        exclusions = [
            StandardProvision(
                provision_name=excl["provision_name"],
                provision_type="exclusion",
                provision_number=excl.get("provision_number"),
                source_form=form_id,
                form_section=excl.get("form_section"),
                description=excl.get("description"),
                sub_provisions=excl.get("sub_provisions"),
                confidence=0.95,
            )
            for excl in form_data.get("exclusions", [])
        ]

        conditions = [
            StandardProvision(
                provision_name=cond["provision_name"],
                provision_type="condition",
                provision_number=cond.get("provision_number"),
                source_form=form_id,
                form_section=cond.get("form_section"),
                description=cond.get("description"),
                sub_provisions=cond.get("sub_provisions"),
                confidence=0.95,
            )
            for cond in form_data.get("conditions", [])
        ]

        return BaseFormExtractionResult(
            form_id=form_id,
            form_name=form_data.get("form_name", form_id),
            coverages=coverages,
            exclusions=exclusions,
            conditions=conditions,
            extraction_confidence=0.95,
        )

    async def _extract_with_llm(
        self,
        document_text: str
    ) -> BaseFormExtractionResult:
        """Extract provisions using LLM.

        Args:
            document_text: The document text to extract from.

        Returns:
            BaseFormExtractionResult from LLM extraction.
        """
        try:
            response = await self.client.generate_content(
                contents=f"Extract all provisions from this base policy form:\n\n{document_text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )

            parsed = parse_json_safely(response)
            if not parsed:
                self.logger.warning("Failed to parse LLM response for base form extraction")
                return BaseFormExtractionResult(
                    form_id="UNKNOWN",
                    form_name="Unknown Form",
                    extraction_confidence=0.0,
                )

            return self._parse_llm_result(parsed)

        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}", exc_info=True)
            return BaseFormExtractionResult(
                form_id="UNKNOWN",
                form_name="Unknown Form",
                extraction_confidence=0.0,
            )

    def _parse_llm_result(self, parsed: Dict[str, Any]) -> BaseFormExtractionResult:
        """Parse LLM extraction result into BaseFormExtractionResult.

        Args:
            parsed: Parsed JSON from LLM.

        Returns:
            BaseFormExtractionResult.
        """
        form_id = parsed.get("form_id", "UNKNOWN")
        form_name = parsed.get("form_name", "Unknown Form")

        coverages = []
        for cov in parsed.get("coverages", []):
            coverages.append(StandardProvision(
                provision_name=cov.get("provision_name", "Unknown Coverage"),
                provision_type="coverage",
                provision_number=cov.get("provision_number"),
                source_form=form_id,
                form_section=cov.get("form_section"),
                description=cov.get("description"),
                verbatim_text=cov.get("verbatim_text"),
                sub_provisions=cov.get("sub_provisions"),
                confidence=float(cov.get("confidence", 0.8)),
            ))

        exclusions = []
        for excl in parsed.get("exclusions", []):
            exclusions.append(StandardProvision(
                provision_name=excl.get("provision_name", "Unknown Exclusion"),
                provision_type="exclusion",
                provision_number=excl.get("provision_number"),
                source_form=form_id,
                form_section=excl.get("form_section"),
                description=excl.get("description"),
                verbatim_text=excl.get("verbatim_text"),
                sub_provisions=excl.get("sub_provisions"),
                confidence=float(excl.get("confidence", 0.8)),
            ))

        conditions = []
        for cond in parsed.get("conditions", []):
            conditions.append(StandardProvision(
                provision_name=cond.get("provision_name", "Unknown Condition"),
                provision_type="condition",
                provision_number=cond.get("provision_number"),
                source_form=form_id,
                form_section=cond.get("form_section"),
                description=cond.get("description"),
                verbatim_text=cond.get("verbatim_text"),
                sub_provisions=cond.get("sub_provisions"),
                confidence=float(cond.get("confidence", 0.8)),
            ))

        definitions = []
        for defn in parsed.get("definitions", []):
            definitions.append(StandardProvision(
                provision_name=defn.get("provision_name", "Unknown Definition"),
                provision_type="definition",
                provision_number=defn.get("provision_number"),
                source_form=form_id,
                form_section=defn.get("form_section"),
                description=defn.get("description"),
                verbatim_text=defn.get("verbatim_text"),
                confidence=float(defn.get("confidence", 0.8)),
            ))

        return BaseFormExtractionResult(
            form_id=form_id,
            form_name=form_name,
            form_edition_date=parsed.get("form_edition_date"),
            coverages=coverages,
            exclusions=exclusions,
            conditions=conditions,
            definitions=definitions,
            extraction_confidence=float(parsed.get("confidence", 0.8)),
        )

    def _merge_results(
        self,
        kb_result: BaseFormExtractionResult,
        llm_result: BaseFormExtractionResult
    ) -> BaseFormExtractionResult:
        """Merge knowledge base and LLM extraction results.

        Knowledge base provides canonical structure, LLM provides document-specific
        details like verbatim text and additional discovered provisions.

        Args:
            kb_result: Result from knowledge base.
            llm_result: Result from LLM extraction.

        Returns:
            Merged BaseFormExtractionResult.
        """
        # Use KB as base, enhance with LLM details
        merged_coverages = list(kb_result.coverages)
        merged_exclusions = list(kb_result.exclusions)
        merged_conditions = list(kb_result.conditions)
        merged_definitions = list(kb_result.definitions)

        # Create lookup for KB items by name
        kb_coverage_names = {c.provision_name.lower() for c in kb_result.coverages}
        kb_exclusion_names = {e.provision_name.lower() for e in kb_result.exclusions}
        kb_condition_names = {c.provision_name.lower() for c in kb_result.conditions}

        # Add LLM items not in KB (may have discovered additional provisions)
        for cov in llm_result.coverages:
            if cov.provision_name.lower() not in kb_coverage_names:
                cov.confidence = min(cov.confidence, 0.85)  # Lower confidence for discovered items
                merged_coverages.append(cov)

        for excl in llm_result.exclusions:
            if excl.provision_name.lower() not in kb_exclusion_names:
                excl.confidence = min(excl.confidence, 0.85)
                merged_exclusions.append(excl)

        for cond in llm_result.conditions:
            if cond.provision_name.lower() not in kb_condition_names:
                cond.confidence = min(cond.confidence, 0.85)
                merged_conditions.append(cond)

        # Add all definitions from LLM (KB typically doesn't have definitions)
        merged_definitions.extend(llm_result.definitions)

        # Update edition date if LLM found it
        edition_date = kb_result.form_edition_date or llm_result.form_edition_date

        return BaseFormExtractionResult(
            form_id=kb_result.form_id,
            form_name=kb_result.form_name,
            form_edition_date=edition_date,
            coverages=merged_coverages,
            exclusions=merged_exclusions,
            conditions=merged_conditions,
            definitions=merged_definitions,
            extraction_confidence=max(
                kb_result.extraction_confidence,
                llm_result.extraction_confidence * 0.9
            ),
        )

    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response (BaseExtractor interface).

        Args:
            parsed: Parsed LLM response.

        Returns:
            Extracted fields dictionary.
        """
        return {
            "form_id": parsed.get("form_id"),
            "form_name": parsed.get("form_name"),
            "coverages": parsed.get("coverages", []),
            "exclusions": parsed.get("exclusions", []),
            "conditions": parsed.get("conditions", []),
            "definitions": parsed.get("definitions", []),
        }
