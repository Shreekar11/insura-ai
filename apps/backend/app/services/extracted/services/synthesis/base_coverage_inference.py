"""Base Coverage Inference Service - LLM fallback for low-confidence synthesis.

When synthesis confidence is below threshold (0.7), this service uses LLM
to infer base coverage context from referenced form numbers.
"""

from typing import Dict, List, Any, Optional

from app.utils.json_parser import parse_json_safely
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


BASE_COVERAGE_INFERENCE_PROMPT = """You are an insurance policy analyst. Given form number references from endorsements, infer what base coverages these forms typically provide.

## TASK
Analyze the provided form references and describe the typical coverage structure they represent.

## FORM REFERENCES
{form_references}

## OUTPUT FORMAT
Return valid JSON with this structure:
{{
    "inferred_coverages": [
        {{
            "coverage_name": "Name of the coverage",
            "typical_terms": {{
                "term_name": "Covered | Not Covered (standard) | Varies"
            }},
            "form_reference": "The form number this relates to",
            "description": "Brief description of what this coverage typically includes"
        }}
    ],
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of the inference"
}}

## RULES
1. Only infer coverages for well-known ISO or standard forms
2. Be conservative - if unsure, set confidence lower
3. Mark typical exclusions as "Not Covered (standard)"
4. Note variations where endorsements commonly modify terms
"""


class BaseCoverageInferenceService:
    """Service for inferring base coverage context using LLM.

    This is the fallback mechanism when primary synthesis confidence
    is below the threshold. It uses LLM to infer what the referenced
    base policy forms typically cover.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
    ):
        """Initialize the inference service.

        Args:
            provider: LLM provider name.
            gemini_api_key: Gemini API key.
            gemini_model: Gemini model name.
            openrouter_api_key: OpenRouter API key.
            openrouter_model: OpenRouter model name.
            openrouter_api_url: OpenRouter API URL.
        """
        self._provider = provider
        self._gemini_api_key = gemini_api_key
        self._gemini_model = gemini_model
        self._openrouter_api_key = openrouter_api_key
        self._openrouter_model = openrouter_model
        self._openrouter_api_url = openrouter_api_url
        self._client = None
        self.logger = LOGGER

    @property
    def client(self):
        """Lazy initialization of LLM client."""
        if self._client is None:
            # Lazy import to avoid import-time dependency on google.genai
            from app.core.unified_llm import create_llm_client_from_settings
            self._client = create_llm_client_from_settings(
                provider=self._provider or "gemini",
                gemini_api_key=self._gemini_api_key or "",
                gemini_model=self._gemini_model,
                openrouter_api_key=self._openrouter_api_key,
                openrouter_model=self._openrouter_model,
                openrouter_api_url=self._openrouter_api_url,
            )
        return self._client

    @client.setter
    def client(self, value):
        """Allow setting client for testing."""
        self._client = value

    async def infer_base_coverages(
        self,
        form_references: List[str],
        endorsement_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Infer base coverages from form references.

        Args:
            form_references: List of form numbers/names referenced in endorsements.
            endorsement_context: Optional additional context from endorsements.

        Returns:
            Dict with inferred_coverages, confidence, and reasoning.
        """
        if not form_references:
            return {
                "inferred_coverages": [],
                "confidence": 0.0,
                "reasoning": "No form references provided",
            }

        # Deduplicate and format references
        unique_refs = list(set(form_references))
        refs_text = "\n".join(f"- {ref}" for ref in unique_refs)

        # Add endorsement context if provided
        if endorsement_context:
            refs_text += f"\n\nAdditional context:\n{endorsement_context}"

        prompt = BASE_COVERAGE_INFERENCE_PROMPT.format(form_references=refs_text)

        try:
            response = await self.client.generate_content(
                contents=f"Infer base coverages from these form references:\n\n{refs_text}",
                system_instruction=prompt,
                generation_config={"response_mime_type": "application/json"}
            )

            parsed = parse_json_safely(response)

            if parsed:
                return parsed
            else:
                self.logger.warning("Failed to parse LLM inference response")
                return {
                    "inferred_coverages": [],
                    "confidence": 0.0,
                    "reasoning": "Failed to parse inference response",
                }

        except Exception as e:
            self.logger.error(f"Base coverage inference failed: {e}", exc_info=True)
            return {
                "inferred_coverages": [],
                "confidence": 0.0,
                "reasoning": f"Inference failed: {str(e)}",
            }

    def extract_form_references(
        self,
        endorsement_data: Dict[str, Any],
    ) -> List[str]:
        """Extract form references from endorsement data.

        Args:
            endorsement_data: Endorsement extraction output.

        Returns:
            List of unique form references.
        """
        references = set()

        # From basic endorsements
        endorsements = endorsement_data.get("endorsements", [])
        for endo in endorsements:
            impacted = endo.get("impacted_coverage", "")
            if impacted:
                # Extract form-like patterns
                references.add(impacted)

        # From projection endorsements
        proj_endorsements = endorsement_data.get("endorsements", [])
        for endo in proj_endorsements:
            # Get the endorsement number as a reference
            endo_num = endo.get("endorsement_number")
            if endo_num:
                references.add(endo_num)

            # Get referenced sections from modifications
            for mod in endo.get("modifications", []):
                ref_section = mod.get("referenced_section")
                if ref_section:
                    references.add(ref_section)

        return list(references)
