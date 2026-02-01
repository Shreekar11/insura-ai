"""Endorsement Provision Extractor - extracts individual provisions from endorsements.

This service extracts individual lettered provisions (A-N) from endorsements like
"BUSINESS AUTO EXTENSION ENDORSEMENT" (CA T3 53) which contain multiple coverage
modifications in a single endorsement.

The extractor handles:
1. Multi-provision endorsements with lettered sections
2. Schedule-based endorsements with blanket entries
3. Coverage modifications with scope/limit changes
"""

from typing import Dict, List, Any, Optional
from uuid import UUID
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


@dataclass
class EndorsementProvision:
    """A single provision within an endorsement."""
    provision_letter: str  # A, B, C, etc.
    provision_name: str
    provision_type: str  # coverage_addition | coverage_expansion | coverage_restriction | exclusion_modification
    effect_category: str  # adds_coverage | expands_coverage | limits_coverage | restores_coverage
    impacted_coverage: Optional[str] = None
    impacted_exclusion: Optional[str] = None
    scope_modification: Optional[str] = None
    limit_modification: Optional[str] = None
    deductible_modification: Optional[str] = None
    condition_modification: Optional[str] = None
    verbatim_text: Optional[str] = None
    schedule_reference: Optional[str] = None
    is_blanket: bool = False
    confidence: float = 0.85


@dataclass
class EndorsementProvisionResult:
    """Result of extracting provisions from an endorsement."""
    endorsement_number: str
    endorsement_name: str
    form_edition_date: Optional[str] = None
    provisions: List[EndorsementProvision] = field(default_factory=list)
    schedule_items: Optional[List[Dict[str, Any]]] = None
    overall_effect: str = "mixed"  # expansive | restrictive | mixed | neutral
    confidence: float = 0.85


# Prompt for endorsement provision extraction
ENDORSEMENT_PROVISION_EXTRACTION_PROMPT = """You are an expert insurance policy analyst specializing in endorsement analysis.

Your task is to extract EACH INDIVIDUAL PROVISION from this endorsement, identifying:
1. The provision letter/number (A, B, C, etc.)
2. What coverage or exclusion it modifies
3. How it modifies coverage (expands, restricts, adds, removes)
4. Any limits, deductibles, or conditions associated with the provision

IMPORTANT RULES:
1. Extract EVERY lettered or numbered provision separately
2. For each provision, determine if it EXPANDS or RESTRICTS coverage
3. Identify any schedule references (amounts, limits, parties)
4. Preserve verbatim language where significant
5. Note if a provision applies on a "blanket" basis (no schedule entry required)

PROVISION TYPES:
- coverage_addition: Adds entirely new coverage
- coverage_expansion: Broadens existing coverage scope or limits
- coverage_restriction: Narrows existing coverage
- exclusion_modification: Modifies or removes an exclusion
- condition_modification: Changes policy conditions

EFFECT CATEGORIES:
- adds_coverage: New coverage not in base policy
- expands_coverage: Broadens scope of existing coverage
- limits_coverage: Restricts or narrows coverage
- restores_coverage: Removes or narrows an exclusion

OUTPUT FORMAT (strict JSON):
{
  "endorsement_number": "CA T3 53",
  "endorsement_name": "BUSINESS AUTO EXTENSION ENDORSEMENT",
  "form_edition_date": "02 15",
  "provisions": [
    {
      "provision_letter": "A",
      "provision_name": "BLANKET ADDITIONAL INSURED",
      "provision_type": "coverage_expansion",
      "effect_category": "expands_coverage",
      "impacted_coverage": "Covered Autos Liability Coverage",
      "scope_modification": "Extends who qualifies as insured to include persons required by written contract",
      "limit_modification": null,
      "condition_modification": "Only if required by written contract executed before loss",
      "verbatim_text": "Any person or organization who is required under a written contract...",
      "is_blanket": true,
      "confidence": 0.95
    },
    {
      "provision_letter": "B",
      "provision_name": "BLANKET WAIVER OF SUBROGATION",
      "provision_type": "exclusion_modification",
      "effect_category": "restores_coverage",
      "impacted_exclusion": "Transfer of Rights of Recovery",
      "scope_modification": "Waives subrogation rights against persons/organizations required by contract",
      "condition_modification": "Written contract must be executed before loss",
      "is_blanket": true,
      "confidence": 0.95
    }
  ],
  "schedule_items": [
    {
      "item_type": "Additional Insured",
      "designated_person_org": "Per Written Contract",
      "applies_to_provision": "A"
    }
  ],
  "overall_effect": "expansive",
  "confidence": 0.93
}

Extract ALL provisions, even minor ones. Each provision should be a separate entry.
"""


class EndorsementProvisionExtractor(BaseExtractor):
    """Extracts individual provisions from multi-provision endorsements.

    This extractor handles complex endorsements that contain multiple
    coverage modifications, such as:
    - Business Auto Extension Endorsement (CA T3 53)
    - Commercial General Liability Extension Endorsement
    - Blanket endorsements with multiple provisions

    Attributes:
        logger: Logger instance.
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
    ):
        """Initialize endorsement provision extractor.

        Args:
            session: SQLAlchemy async session.
            provider: LLM provider.
            gemini_api_key: Gemini API key.
            gemini_model: Gemini model name.
            openrouter_api_key: OpenRouter API key.
            openrouter_model: OpenRouter model name.
            openrouter_api_url: OpenRouter API URL.
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
        self.logger = LOGGER

    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for endorsement provisions."""
        return ENDORSEMENT_PROVISION_EXTRACTION_PROMPT

    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract provisions from endorsement text.

        Args:
            text: The endorsement text to extract from.
            document_id: Document ID for tracking.
            chunk_id: Optional chunk ID.

        Returns:
            List containing the extraction result.
        """
        result = await self.extract_provisions(text)
        return [self._result_to_dict(result)]

    async def extract_provisions(
        self,
        endorsement_text: str,
        endorsement_number: Optional[str] = None,
    ) -> EndorsementProvisionResult:
        """Extract all provisions from an endorsement.

        Args:
            endorsement_text: The endorsement text.
            endorsement_number: Optional endorsement number if already known.

        Returns:
            EndorsementProvisionResult with all extracted provisions.
        """
        self.logger.info(
            f"Extracting provisions from endorsement",
            extra={"endorsement_number": endorsement_number}
        )

        try:
            response = await self.client.generate_content(
                contents=f"Extract all provisions from this endorsement:\n\n{endorsement_text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )

            parsed = parse_json_safely(response)
            if not parsed:
                self.logger.warning("Failed to parse LLM response for provision extraction")
                return self._create_empty_result(endorsement_number)

            return self._parse_result(parsed)

        except Exception as e:
            self.logger.error(f"Provision extraction failed: {e}", exc_info=True)
            return self._create_empty_result(endorsement_number)

    async def extract_provisions_batch(
        self,
        endorsement_texts: List[str],
    ) -> List[EndorsementProvisionResult]:
        """Extract provisions from multiple endorsements.

        Args:
            endorsement_texts: List of endorsement texts.

        Returns:
            List of EndorsementProvisionResult.
        """
        results = []
        for text in endorsement_texts:
            result = await self.extract_provisions(text)
            results.append(result)
        return results

    def identify_provision_type(
        self,
        provision_text: str,
        provision_name: str,
    ) -> str:
        """Identify the type of a provision based on its text.

        Args:
            provision_text: The provision text.
            provision_name: The provision name.

        Returns:
            Provision type string.
        """
        text_lower = provision_text.lower()
        name_lower = provision_name.lower()

        # Check for coverage addition indicators
        if any(phrase in text_lower for phrase in [
            "coverage is extended",
            "coverage is added",
            "the following coverage",
            "we will pay",
        ]):
            if any(phrase in text_lower for phrase in ["not in", "new", "additional"]):
                return "coverage_addition"
            return "coverage_expansion"

        # Check for restriction indicators
        if any(phrase in text_lower for phrase in [
            "does not apply",
            "is limited to",
            "only if",
            "subject to",
        ]):
            return "coverage_restriction"

        # Check for exclusion modification
        if any(phrase in text_lower for phrase in [
            "exclusion does not apply",
            "notwithstanding",
            "waiver",
            "waived",
        ]):
            return "exclusion_modification"

        # Check for condition modification
        if any(phrase in name_lower for phrase in [
            "condition",
            "duties",
            "notice",
            "cooperation",
        ]):
            return "condition_modification"

        # Default to expansion for most endorsement provisions
        return "coverage_expansion"

    def identify_effect_category(
        self,
        provision_type: str,
        provision_text: str,
    ) -> str:
        """Identify the effect category of a provision.

        Args:
            provision_type: The provision type.
            provision_text: The provision text.

        Returns:
            Effect category string.
        """
        text_lower = provision_text.lower()

        if provision_type == "coverage_addition":
            return "adds_coverage"

        if provision_type == "exclusion_modification":
            # Check if it's removing/narrowing an exclusion (restoring coverage)
            if any(phrase in text_lower for phrase in [
                "exclusion does not apply",
                "waived",
                "is deleted",
            ]):
                return "restores_coverage"
            return "limits_coverage"

        if provision_type == "coverage_restriction":
            return "limits_coverage"

        if provision_type == "coverage_expansion":
            return "expands_coverage"

        return "expands_coverage"

    def _parse_result(self, parsed: Dict[str, Any]) -> EndorsementProvisionResult:
        """Parse LLM result into EndorsementProvisionResult.

        Args:
            parsed: Parsed JSON from LLM.

        Returns:
            EndorsementProvisionResult.
        """
        provisions = []

        for prov in parsed.get("provisions", []):
            provisions.append(EndorsementProvision(
                provision_letter=prov.get("provision_letter", ""),
                provision_name=prov.get("provision_name", "Unknown Provision"),
                provision_type=prov.get("provision_type", "coverage_expansion"),
                effect_category=prov.get("effect_category", "expands_coverage"),
                impacted_coverage=prov.get("impacted_coverage"),
                impacted_exclusion=prov.get("impacted_exclusion"),
                scope_modification=prov.get("scope_modification"),
                limit_modification=prov.get("limit_modification"),
                deductible_modification=prov.get("deductible_modification"),
                condition_modification=prov.get("condition_modification"),
                verbatim_text=prov.get("verbatim_text"),
                schedule_reference=prov.get("schedule_reference"),
                is_blanket=prov.get("is_blanket", False),
                confidence=float(prov.get("confidence", 0.85)),
            ))

        return EndorsementProvisionResult(
            endorsement_number=parsed.get("endorsement_number", "UNKNOWN"),
            endorsement_name=parsed.get("endorsement_name", "Unknown Endorsement"),
            form_edition_date=parsed.get("form_edition_date"),
            provisions=provisions,
            schedule_items=parsed.get("schedule_items"),
            overall_effect=parsed.get("overall_effect", "mixed"),
            confidence=float(parsed.get("confidence", 0.85)),
        )

    def _create_empty_result(
        self,
        endorsement_number: Optional[str]
    ) -> EndorsementProvisionResult:
        """Create empty result for failed extraction.

        Args:
            endorsement_number: The endorsement number if known.

        Returns:
            Empty EndorsementProvisionResult.
        """
        return EndorsementProvisionResult(
            endorsement_number=endorsement_number or "UNKNOWN",
            endorsement_name="Unknown Endorsement",
            provisions=[],
            confidence=0.0,
        )

    def _result_to_dict(self, result: EndorsementProvisionResult) -> Dict[str, Any]:
        """Convert result to dictionary.

        Args:
            result: EndorsementProvisionResult.

        Returns:
            Dictionary representation.
        """
        return {
            "endorsement_number": result.endorsement_number,
            "endorsement_name": result.endorsement_name,
            "form_edition_date": result.form_edition_date,
            "provisions": [
                {
                    "provision_letter": p.provision_letter,
                    "provision_name": p.provision_name,
                    "provision_type": p.provision_type,
                    "effect_category": p.effect_category,
                    "impacted_coverage": p.impacted_coverage,
                    "impacted_exclusion": p.impacted_exclusion,
                    "scope_modification": p.scope_modification,
                    "limit_modification": p.limit_modification,
                    "deductible_modification": p.deductible_modification,
                    "condition_modification": p.condition_modification,
                    "verbatim_text": p.verbatim_text,
                    "schedule_reference": p.schedule_reference,
                    "is_blanket": p.is_blanket,
                    "confidence": p.confidence,
                }
                for p in result.provisions
            ],
            "schedule_items": result.schedule_items,
            "overall_effect": result.overall_effect,
            "confidence": result.confidence,
        }

    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response (BaseExtractor interface).

        Args:
            parsed: Parsed LLM response.

        Returns:
            Extracted fields dictionary.
        """
        return {
            "endorsement_number": parsed.get("endorsement_number"),
            "endorsement_name": parsed.get("endorsement_name"),
            "provisions": parsed.get("provisions", []),
            "schedule_items": parsed.get("schedule_items"),
            "overall_effect": parsed.get("overall_effect"),
        }


# Known multi-provision endorsements for pattern recognition
KNOWN_MULTI_PROVISION_ENDORSEMENTS = {
    "CA T3 53": {
        "name": "Business Auto Extension Endorsement",
        "typical_provisions": [
            "Blanket Additional Insured",
            "Blanket Waiver of Subrogation",
            "Employees as Additional Insureds",
            "Primary Insurance",
            "Physical Damage Coverage Extensions",
            "Towing and Labor",
            "Personal Effects",
            "Rental Reimbursement",
            "Audio, Visual and Data Electronic Equipment",
            "Airbag Coverage",
            "Glass Breakage",
            "Transportation Expenses",
            "Loss of Use Expenses",
            "Lease Gap Coverage",
        ],
        "overall_effect": "expansive",
    },
    "CG 24 26": {
        "name": "Additional Insured - Designated Person Or Organization",
        "typical_provisions": [
            "Additional Insured Status",
        ],
        "overall_effect": "expansive",
    },
    "CG 20 10": {
        "name": "Additional Insured - Owners, Lessees Or Contractors",
        "typical_provisions": [
            "Additional Insured for Ongoing Operations",
        ],
        "overall_effect": "expansive",
    },
}


def get_known_endorsement_info(endorsement_number: str) -> Optional[Dict[str, Any]]:
    """Get known information about a multi-provision endorsement.

    Args:
        endorsement_number: The endorsement form number.

    Returns:
        Dictionary with endorsement information or None.
    """
    # Normalize the endorsement number
    normalized = endorsement_number.upper().replace(" ", "").replace("-", "")

    for known_number, info in KNOWN_MULTI_PROVISION_ENDORSEMENTS.items():
        known_normalized = known_number.upper().replace(" ", "").replace("-", "")
        if known_normalized == normalized or known_number == endorsement_number:
            return info

    return None
