"""Synthesis Orchestrator - coordinates coverage and exclusion synthesis.

This service orchestrates the post-extraction synthesis process:
1. Extracts endorsement data from extraction results
2. Runs coverage synthesis
3. Runs exclusion synthesis
4. Optionally triggers LLM fallback for low confidence
5. Merges results into final output
"""

from typing import Dict, List, Any, Optional

from app.services.extracted.services.synthesis.coverage_synthesizer import CoverageSynthesizer
from app.services.extracted.services.synthesis.exclusion_synthesizer import ExclusionSynthesizer
from app.services.extracted.services.synthesis.base_coverage_inference import BaseCoverageInferenceService
from app.schemas.product.synthesis_models import SynthesisResult, SynthesisMethod
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Default confidence threshold for triggering LLM fallback
DEFAULT_CONFIDENCE_THRESHOLD = 0.7


class SynthesisOrchestrator:
    """Orchestrates the synthesis of effective coverages and exclusions.

    This service is the main entry point for post-extraction synthesis.
    It coordinates CoverageSynthesizer and ExclusionSynthesizer, and
    optionally triggers LLM inference fallback for low-confidence results.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        enable_llm_fallback: bool = True,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
    ):
        """Initialize the synthesis orchestrator.

        Args:
            confidence_threshold: Threshold below which LLM fallback is triggered.
            enable_llm_fallback: Whether to enable LLM inference fallback.
            provider: LLM provider for fallback.
            gemini_api_key: Gemini API key.
            gemini_model: Gemini model name.
            openrouter_api_key: OpenRouter API key.
            openrouter_model: OpenRouter model name.
            openrouter_api_url: OpenRouter API URL.
        """
        self.confidence_threshold = confidence_threshold
        self.enable_llm_fallback = enable_llm_fallback

        # Initialize synthesizers
        self.coverage_synthesizer = CoverageSynthesizer()
        self.exclusion_synthesizer = ExclusionSynthesizer()

        # Initialize inference service (lazy - only used if fallback triggered)
        self._inference_service = None
        self._llm_config = {
            "provider": provider,
            "gemini_api_key": gemini_api_key,
            "gemini_model": gemini_model,
            "openrouter_api_key": openrouter_api_key,
            "openrouter_model": openrouter_model,
            "openrouter_api_url": openrouter_api_url,
        }

        self.logger = LOGGER

    @property
    def inference_service(self) -> BaseCoverageInferenceService:
        """Lazy initialization of inference service."""
        if self._inference_service is None:
            self._inference_service = BaseCoverageInferenceService(**self._llm_config)
        return self._inference_service

    def synthesize(
        self,
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize effective coverages and exclusions from extraction result.

        Args:
            extraction_result: The DocumentExtractionResult.to_dict() output.

        Returns:
            Dict with effective_coverages, effective_exclusions, and metadata.
        """
        # Extract endorsement data from section results
        endorsement_data, endorsement_modifications, exclusion_modifications = (
            self._extract_endorsement_data(extraction_result)
        )

        # Extract base coverages/exclusions if present
        base_coverages = self._extract_base_section(extraction_result, "coverages")
        base_exclusions = self._extract_base_section(extraction_result, "exclusions")

        # Run coverage synthesis
        coverage_result = self.coverage_synthesizer.synthesize_coverages(
            endorsement_modifications=endorsement_modifications,
            endorsement_data=endorsement_data,
            base_coverages=base_coverages,
        )

        # Run exclusion synthesis
        exclusion_result = self.exclusion_synthesizer.synthesize_exclusions(
            exclusion_modifications=exclusion_modifications,
            endorsement_data=endorsement_data,
            base_exclusions=base_exclusions,
        )

        # Merge results
        merged = self._merge_results(coverage_result, exclusion_result)

        # Check if fallback is needed
        if merged["overall_confidence"] < self.confidence_threshold and self.enable_llm_fallback:
            merged["fallback_recommended"] = True
            self.logger.info(
                f"Synthesis confidence {merged['overall_confidence']:.2f} below threshold "
                f"{self.confidence_threshold}, LLM fallback recommended"
            )
        else:
            merged["fallback_recommended"] = False

        return merged

    async def synthesize_with_fallback(
        self,
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize with automatic LLM fallback for low confidence.

        Args:
            extraction_result: The DocumentExtractionResult.to_dict() output.

        Returns:
            Dict with effective_coverages, effective_exclusions, and metadata.
        """
        # First, run standard synthesis
        result = self.synthesize(extraction_result)

        # If confidence is low and fallback is enabled, run inference
        if result.get("fallback_recommended") and self.enable_llm_fallback:
            self.logger.info("Running LLM inference fallback for low-confidence synthesis")

            # Extract form references for inference
            endorsement_data, _, _ = self._extract_endorsement_data(extraction_result)
            form_refs = self.inference_service.extract_form_references(endorsement_data or {})

            if form_refs:
                inference_result = await self.inference_service.infer_base_coverages(form_refs)

                # Merge inferred coverages with synthesis result
                if inference_result.get("inferred_coverages"):
                    result = self._merge_inferred_coverages(result, inference_result)
                    result["synthesis_method"] = SynthesisMethod.LLM_INFERENCE.value
                    result["fallback_used"] = True

        return result

    def augment_extraction_result(
        self,
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Augment extraction result with synthesis output.

        This preserves the original extraction structure while adding
        effective_coverages and effective_exclusions at the top level.

        Args:
            extraction_result: The original extraction result dict.

        Returns:
            Augmented extraction result with synthesis data.
        """
        synthesis = self.synthesize(extraction_result)

        # Create augmented result preserving original structure
        augmented = dict(extraction_result)
        augmented["effective_coverages"] = synthesis.get("effective_coverages", [])
        augmented["effective_exclusions"] = synthesis.get("effective_exclusions", [])
        augmented["synthesis_metadata"] = {
            "overall_confidence": synthesis.get("overall_confidence", 0.0),
            "synthesis_method": synthesis.get("synthesis_method", "endorsement_only"),
            "fallback_recommended": synthesis.get("fallback_recommended", False),
            "source_endorsement_count": synthesis.get("source_endorsement_count", 0),
        }

        return augmented

    def _extract_endorsement_data(
        self,
        extraction_result: Dict[str, Any],
    ) -> tuple:
        """Extract endorsement data from extraction result.

        Args:
            extraction_result: The extraction result dict.

        Returns:
            Tuple of (endorsement_data, endorsement_modifications, exclusion_modifications)
        """
        endorsement_data = None
        endorsement_modifications = None
        exclusion_modifications = None

        section_results = extraction_result.get("section_results", [])

        for section in section_results:
            section_type = section.get("section_type", "")
            extracted_data = section.get("extracted_data", {})

            if section_type == "endorsements":
                # Check if this is projection data (has "modifications" key in endorsements)
                endorsements = extracted_data.get("endorsements", [])

                has_modifications = any(
                    "modifications" in endo for endo in endorsements
                )

                if has_modifications:
                    # This is projection data - check for coverage vs exclusion
                    # For now, treat as coverage modifications (most common)
                    endorsement_modifications = extracted_data
                else:
                    # This is basic endorsement data
                    endorsement_data = extracted_data

            # Future: handle dedicated exclusion projection section type

        return endorsement_data, endorsement_modifications, exclusion_modifications

    def _extract_base_section(
        self,
        extraction_result: Dict[str, Any],
        section_type: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Extract base section data (coverages or exclusions).

        Args:
            extraction_result: The extraction result dict.
            section_type: "coverages" or "exclusions"

        Returns:
            List of section items or None.
        """
        section_results = extraction_result.get("section_results", [])

        for section in section_results:
            if section.get("section_type") == section_type:
                extracted_data = section.get("extracted_data", {})
                return extracted_data.get(section_type, [])

        return None

    def _merge_results(
        self,
        coverage_result: SynthesisResult,
        exclusion_result: SynthesisResult,
    ) -> Dict[str, Any]:
        """Merge coverage and exclusion synthesis results.

        Args:
            coverage_result: Result from CoverageSynthesizer.
            exclusion_result: Result from ExclusionSynthesizer.

        Returns:
            Merged result dict.
        """
        # Calculate combined confidence
        confidences = []
        if coverage_result.effective_coverages:
            confidences.append(coverage_result.overall_confidence)
        if exclusion_result.effective_exclusions:
            confidences.append(exclusion_result.overall_confidence)

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "effective_coverages": [c.model_dump() for c in coverage_result.effective_coverages],
            "effective_exclusions": [e.model_dump() for e in exclusion_result.effective_exclusions],
            "overall_confidence": overall_confidence,
            "synthesis_method": coverage_result.synthesis_method,
            "source_endorsement_count": (
                coverage_result.source_endorsement_count +
                exclusion_result.source_endorsement_count
            ),
        }

    def _merge_inferred_coverages(
        self,
        synthesis_result: Dict[str, Any],
        inference_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge inferred coverages into synthesis result.

        Args:
            synthesis_result: Current synthesis result.
            inference_result: LLM inference result.

        Returns:
            Enhanced synthesis result.
        """
        inferred = inference_result.get("inferred_coverages", [])
        existing_names = {c["coverage_name"] for c in synthesis_result.get("effective_coverages", [])}

        for inferred_cov in inferred:
            cov_name = inferred_cov.get("coverage_name")
            if cov_name and cov_name not in existing_names:
                # Convert inferred format to effective coverage format
                synthesis_result["effective_coverages"].append({
                    "coverage_name": cov_name,
                    "effective_terms": inferred_cov.get("typical_terms", {}),
                    "sources": [inferred_cov.get("form_reference", "Inferred")],
                    "confidence": inference_result.get("confidence", 0.7),
                    "reasoning": f"Inferred from {inferred_cov.get('form_reference', 'form reference')}",
                })

        # Boost confidence with inference data
        if inferred:
            current_conf = synthesis_result.get("overall_confidence", 0.0)
            inference_conf = inference_result.get("confidence", 0.7)
            # Weighted average favoring the higher confidence
            synthesis_result["overall_confidence"] = max(current_conf, inference_conf * 0.9)

        return synthesis_result
