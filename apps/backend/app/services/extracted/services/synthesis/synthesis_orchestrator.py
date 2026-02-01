"""Synthesis Orchestrator - coordinates coverage and exclusion synthesis.

This service orchestrates the post-extraction synthesis process:
1. Classifies documents as base forms vs endorsements
2. Extracts standard provisions from base forms
3. Extracts endorsement modifications
4. Merges base form provisions with endorsement modifications
5. Generates human-readable descriptions
6. Produces final effective coverages and exclusions

The two-document extraction pipeline handles:
- Base policy forms (CA 00 01, CG 00 01, etc.) with standard provisions
- Endorsement packages that modify base policy terms
"""

from typing import Dict, List, Any, Optional

from app.services.extracted.services.synthesis.coverage_synthesizer import CoverageSynthesizer
from app.services.extracted.services.synthesis.exclusion_synthesizer import ExclusionSynthesizer
from app.services.extracted.services.synthesis.base_coverage_inference import BaseCoverageInferenceService
from app.services.extracted.services.synthesis.description_generator import (
    create_description_generator,
)
from app.services.extracted.services.document_type_classifier import DocumentTypeClassifier
from app.schemas.product.synthesis_models import (
    SynthesisResult,
    SynthesisMethod,
    DocumentCategory,
    StandardProvision,
    BaseFormExtractionResult,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Default confidence threshold for triggering LLM fallback
DEFAULT_CONFIDENCE_THRESHOLD = 0.7


class SynthesisOrchestrator:
    """Orchestrates the synthesis of effective coverages and exclusions.

    This service is the main entry point for post-extraction synthesis.
    It coordinates:
    - DocumentTypeClassifier for identifying base forms vs endorsements
    - BaseFormExtractor for extracting standard provisions
    - CoverageSynthesizer and ExclusionSynthesizer for endorsement modifications
    - DescriptionGenerator for human-readable descriptions
    - Two-document merge logic for combining base form + endorsements

    Attributes:
        confidence_threshold: Threshold below which LLM fallback is triggered.
        enable_llm_fallback: Whether to enable LLM inference fallback.
        enable_two_document_pipeline: Whether to use two-document extraction.
        coverage_synthesizer: Synthesizer for coverage modifications.
        exclusion_synthesizer: Synthesizer for exclusion modifications.
        document_classifier: Classifier for document types.
        description_generator: Generator for human-readable descriptions.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        enable_llm_fallback: bool = True,
        enable_two_document_pipeline: bool = True,
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
            enable_two_document_pipeline: Whether to use two-document extraction.
            provider: LLM provider for fallback.
            gemini_api_key: Gemini API key.
            gemini_model: Gemini model name.
            openrouter_api_key: OpenRouter API key.
            openrouter_model: OpenRouter model name.
            openrouter_api_url: OpenRouter API URL.
        """
        self.confidence_threshold = confidence_threshold
        self.enable_llm_fallback = enable_llm_fallback
        self.enable_two_document_pipeline = enable_two_document_pipeline

        # Initialize synthesizers
        self.coverage_synthesizer = CoverageSynthesizer()
        self.exclusion_synthesizer = ExclusionSynthesizer()

        # Initialize two-document pipeline components
        self.document_classifier = DocumentTypeClassifier()
        self.description_generator = create_description_generator()

        # Initialize inference service (lazy - only used if fallback triggered)
        self._inference_service = None
        self._base_form_extractor = None
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
        base_form_data: Optional[BaseFormExtractionResult] = None,
    ) -> Dict[str, Any]:
        """Synthesize effective coverages and exclusions from extraction result.

        This is the main entry point for synthesis. When two-document pipeline is
        enabled, it will:
        1. Check for base form data in extraction or use provided base_form_data
        2. Extract standard provisions from base forms
        3. Apply endorsement modifications
        4. Generate descriptions for all provisions
        5. Merge into final output

        Args:
            extraction_result: The DocumentExtractionResult.to_dict() output.
            base_form_data: Optional pre-extracted base form data.

        Returns:
            Dict with effective_coverages, effective_exclusions, and metadata.
        """
        # Extract endorsement data from section results
        endorsement_data, endorsement_modifications, exclusion_modifications = (
            self._extract_endorsement_data(extraction_result)
        )

        # Extract base coverages/exclusions if present in extraction
        base_coverages = self._extract_base_section(extraction_result, "coverages")
        base_exclusions = self._extract_base_section(extraction_result, "exclusions")

        # Two-document pipeline: detect and merge base form provisions
        detected_form_id = None
        standard_provisions = None

        if self.enable_two_document_pipeline:
            # Try to detect base form from extraction result
            detected_form_id = self._detect_base_form_from_extraction(extraction_result)

            if detected_form_id or base_form_data:
                self.logger.info(
                    f"Two-document pipeline: Using base form {detected_form_id or base_form_data.form_id}",
                    extra={"form_id": detected_form_id or (base_form_data.form_id if base_form_data else None)}
                )
                standard_provisions = self._get_standard_provisions(
                    detected_form_id,
                    base_form_data
                )

        # Run coverage synthesis with standard provisions
        coverage_result = self.coverage_synthesizer.synthesize_coverages(
            endorsement_modifications=endorsement_modifications,
            endorsement_data=endorsement_data,
            base_coverages=base_coverages,
        )

        # Run exclusion synthesis with standard provisions
        exclusion_result = self.exclusion_synthesizer.synthesize_exclusions(
            exclusion_modifications=exclusion_modifications,
            endorsement_data=endorsement_data,
            base_exclusions=base_exclusions,
        )

        # Merge results with standard provisions
        merged = self._merge_results(coverage_result, exclusion_result)

        # If we have standard provisions from two-document pipeline, merge them
        if standard_provisions:
            merged = self._merge_standard_provisions(
                merged,
                standard_provisions,
                detected_form_id or (base_form_data.form_id if base_form_data else None)
            )
            merged["synthesis_method"] = SynthesisMethod.TWO_DOCUMENT_MERGE.value

        # Generate descriptions for all provisions
        merged = self._add_descriptions(merged)

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

    def synthesize_two_document(
        self,
        base_form_text: str,
        endorsement_text: str,
        extraction_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Synthesize from separate base form and endorsement documents.

        This method handles the case where base form and endorsements are
        provided as separate text documents rather than pre-extracted data.

        Args:
            base_form_text: Text content of the base policy form.
            endorsement_text: Text content of the endorsement package.
            extraction_result: Optional existing extraction result to augment.

        Returns:
            Dict with effective_coverages, effective_exclusions, and metadata.
        """
        self.logger.info("Running two-document synthesis pipeline")

        # Classify the base form
        base_classification = self.document_classifier.classify(base_form_text)

        if base_classification.category != DocumentCategory.BASE_FORM:
            self.logger.warning(
                f"Base form text classified as {base_classification.category}, not BASE_FORM"
            )

        # Extract standard provisions from base form
        base_form_data = self._extract_base_form_provisions(
            base_form_text,
            base_classification.form_id
        )

        # Classify endorsements
        endorsement_classification = self.document_classifier.classify(endorsement_text)

        # If we have an extraction result, use it with base form data
        if extraction_result:
            return self.synthesize(extraction_result, base_form_data)

        # Otherwise, create a synthesis from the two documents directly
        return self._synthesize_from_documents(
            base_form_data,
            endorsement_text,
            endorsement_classification
        )

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
            "base_form_id": synthesis.get("base_form_id"),
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

    def _detect_base_form_from_extraction(
        self,
        extraction_result: Dict[str, Any]
    ) -> Optional[str]:
        """Detect base form ID from extraction result.

        Looks for form references in endorsement data or declarations.

        Args:
            extraction_result: The extraction result dict.

        Returns:
            Detected form ID or None.
        """
        # Check endorsement references
        endorsement_data, _, _ = self._extract_endorsement_data(extraction_result)
        if endorsement_data:
            form_refs = self.document_classifier.extract_form_references(
                str(endorsement_data)
            )
            for ref in form_refs:
                if self.document_classifier.is_base_form_id(ref):
                    return ref

        # Check declarations for policy form
        section_results = extraction_result.get("section_results", [])
        for section in section_results:
            if section.get("section_type") == "declarations":
                extracted = section.get("extracted_data", {})
                policy_form = extracted.get("policy_form")
                if policy_form and self.document_classifier.is_base_form_id(policy_form):
                    return policy_form

        return None

    def _get_standard_provisions(
        self,
        form_id: Optional[str],
        base_form_data: Optional[BaseFormExtractionResult]
    ) -> Optional[Dict[str, List[StandardProvision]]]:
        """Get standard provisions from base form.

        Args:
            form_id: The detected form ID.
            base_form_data: Pre-extracted base form data.

        Returns:
            Dict with 'coverages' and 'exclusions' lists or None.
        """
        if base_form_data:
            return {
                "coverages": base_form_data.coverages,
                "exclusions": base_form_data.exclusions,
                "conditions": base_form_data.conditions,
            }

        if not form_id:
            return None

        # Define standard provisions inline to avoid circular import
        # This is a subset of the knowledge base for commonly-used forms
        STANDARD_FORM_PROVISIONS = self._get_inline_knowledge_base()

        if form_id not in STANDARD_FORM_PROVISIONS:
            return None

        form_data = STANDARD_FORM_PROVISIONS[form_id]

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

        return {
            "coverages": coverages,
            "exclusions": exclusions,
            "conditions": conditions,
        }

    def _merge_standard_provisions(
        self,
        merged_result: Dict[str, Any],
        standard_provisions: Dict[str, List[StandardProvision]],
        form_id: Optional[str]
    ) -> Dict[str, Any]:
        """Merge standard provisions from base form into synthesis result.

        Standard provisions are added with source attribution. If an endorsement
        has modified a standard provision, the modification is noted.

        Args:
            merged_result: Current merged synthesis result.
            standard_provisions: Standard provisions from base form.
            form_id: The base form ID.

        Returns:
            Updated merged result with standard provisions.
        """
        existing_coverages = merged_result.get("effective_coverages", [])
        existing_exclusions = merged_result.get("effective_exclusions", [])

        # Track names of existing items for modification detection
        existing_coverage_names = {
            c.get("coverage_name", "").lower() for c in existing_coverages
        }
        existing_exclusion_names = {
            e.get("exclusion_name", "").lower() for e in existing_exclusions
        }

        # Add standard coverages
        for coverage in standard_provisions.get("coverages", []):
            coverage_name_lower = coverage.provision_name.lower()

            # Check if this coverage was modified by endorsement
            is_modified = coverage_name_lower in existing_coverage_names

            if not is_modified:
                # Add as standard provision
                existing_coverages.append({
                    "coverage_name": coverage.provision_name,
                    "coverage_type": self._infer_coverage_type(coverage.provision_name),
                    "effective_terms": {},
                    "sources": [form_id] if form_id else ["Base Form"],
                    "confidence": coverage.confidence,
                    "description": coverage.description,
                    "source_form": form_id,
                    "is_standard_provision": True,
                    "is_modified": False,
                    "form_section": coverage.form_section,
                })
            else:
                # Find and update the modified coverage
                for cov in existing_coverages:
                    if cov.get("coverage_name", "").lower() == coverage_name_lower:
                        cov["source_form"] = form_id
                        cov["is_standard_provision"] = True
                        cov["is_modified"] = True
                        cov["form_section"] = coverage.form_section
                        # Add base form to sources if not present
                        if form_id and form_id not in cov.get("sources", []):
                            cov["sources"] = [form_id] + cov.get("sources", [])
                        break

        # Add standard exclusions
        for exclusion in standard_provisions.get("exclusions", []):
            exclusion_name_lower = exclusion.provision_name.lower()

            # Check if this exclusion was modified by endorsement
            is_modified = exclusion_name_lower in existing_exclusion_names

            if not is_modified:
                # Add as standard provision
                existing_exclusions.append({
                    "exclusion_name": exclusion.provision_name,
                    "exclusion_number": exclusion.provision_number,
                    "effective_state": "Excluded",
                    "sources": [form_id] if form_id else ["Base Form"],
                    "confidence": exclusion.confidence,
                    "description": exclusion.description,
                    "source_form": form_id,
                    "is_standard_provision": True,
                    "is_modified": False,
                    "form_section": exclusion.form_section,
                    "severity": self.description_generator.get_severity(exclusion.provision_name),
                })
            else:
                # Find and update the modified exclusion
                for excl in existing_exclusions:
                    if excl.get("exclusion_name", "").lower() == exclusion_name_lower:
                        excl["exclusion_number"] = exclusion.provision_number
                        excl["source_form"] = form_id
                        excl["is_standard_provision"] = True
                        excl["is_modified"] = True
                        excl["form_section"] = exclusion.form_section
                        # Add base form to sources if not present
                        if form_id and form_id not in excl.get("sources", []):
                            excl["sources"] = [form_id] + excl.get("sources", [])
                        break

        merged_result["effective_coverages"] = existing_coverages
        merged_result["effective_exclusions"] = existing_exclusions
        merged_result["base_form_id"] = form_id

        # Recalculate confidence with standard provisions
        all_confidences = (
            [c.get("confidence", 0.0) for c in existing_coverages] +
            [e.get("confidence", 0.0) for e in existing_exclusions]
        )
        if all_confidences:
            merged_result["overall_confidence"] = sum(all_confidences) / len(all_confidences)

        self.logger.info(
            f"Merged {len(standard_provisions.get('coverages', []))} standard coverages "
            f"and {len(standard_provisions.get('exclusions', []))} standard exclusions "
            f"from {form_id}"
        )

        return merged_result

    def _add_descriptions(self, merged_result: Dict[str, Any]) -> Dict[str, Any]:
        """Add human-readable descriptions to all provisions.

        Args:
            merged_result: Merged synthesis result.

        Returns:
            Updated result with descriptions.
        """
        # Add descriptions to coverages
        for coverage in merged_result.get("effective_coverages", []):
            if not coverage.get("description"):
                coverage["description"] = self.description_generator.generate_coverage_description(
                    coverage.get("coverage_name", ""),
                    is_modified=coverage.get("is_modified", False),
                    modification_details=coverage.get("modification_details"),
                )

        # Add descriptions to exclusions
        for exclusion in merged_result.get("effective_exclusions", []):
            if not exclusion.get("description"):
                exclusion["description"] = self.description_generator.generate_exclusion_description(
                    exclusion.get("exclusion_name", ""),
                    is_modified=exclusion.get("is_modified", False),
                    modification_details=exclusion.get("modification_details"),
                )

            # Add severity if not present
            if not exclusion.get("severity"):
                exclusion["severity"] = self.description_generator.get_severity(
                    exclusion.get("exclusion_name", "")
                )

        return merged_result

    def _extract_base_form_provisions(
        self,
        base_form_text: str,  # Reserved for future LLM extraction
        form_id: Optional[str]
    ) -> BaseFormExtractionResult:
        """Extract provisions from base form text.

        Currently uses knowledge base lookup. Future versions may use
        LLM extraction from the base_form_text for unknown forms.

        Args:
            base_form_text: The base form text (reserved for future use).
            form_id: The detected form ID.

        Returns:
            BaseFormExtractionResult with extracted provisions.
        """
        # Currently using knowledge base; base_form_text reserved for future LLM extraction
        _ = base_form_text  # Silence unused variable warning

        # Use knowledge base if available
        standard_provisions = self._get_standard_provisions(form_id, None)

        if standard_provisions:
            form_name = self.document_classifier.get_form_name(form_id) or "Unknown Form"
            return BaseFormExtractionResult(
                form_id=form_id or "UNKNOWN",
                form_name=form_name,
                coverages=standard_provisions.get("coverages", []),
                exclusions=standard_provisions.get("exclusions", []),
                conditions=standard_provisions.get("conditions", []),
                extraction_confidence=0.95,
            )

        # Fallback to empty result (LLM extraction would happen in async context)
        return BaseFormExtractionResult(
            form_id=form_id or "UNKNOWN",
            form_name="Unknown Form",
            extraction_confidence=0.5,
        )

    def _synthesize_from_documents(
        self,
        base_form_data: BaseFormExtractionResult,
        endorsement_text: str,  # Reserved for future endorsement parsing
        endorsement_classification: Any  # Reserved for future use
    ) -> Dict[str, Any]:
        """Synthesize directly from documents without extraction result.

        Currently builds output from base form provisions only.
        Future versions will parse endorsement_text to apply modifications.

        Args:
            base_form_data: Extracted base form data.
            endorsement_text: The endorsement text (reserved for future use).
            endorsement_classification: Classification of endorsement document.

        Returns:
            Synthesis result dict.
        """
        # Reserved for future use - silence unused variable warnings
        _ = endorsement_text
        _ = endorsement_classification

        # Build effective coverages from base form
        effective_coverages = []
        for coverage in base_form_data.coverages:
            effective_coverages.append({
                "coverage_name": coverage.provision_name,
                "coverage_type": self._infer_coverage_type(coverage.provision_name),
                "effective_terms": {},
                "sources": [base_form_data.form_id],
                "confidence": coverage.confidence,
                "description": coverage.description,
                "source_form": base_form_data.form_id,
                "is_standard_provision": True,
                "is_modified": False,
                "form_section": coverage.form_section,
            })

        # Build effective exclusions from base form
        effective_exclusions = []
        for exclusion in base_form_data.exclusions:
            effective_exclusions.append({
                "exclusion_name": exclusion.provision_name,
                "exclusion_number": exclusion.provision_number,
                "effective_state": "Excluded",
                "sources": [base_form_data.form_id],
                "confidence": exclusion.confidence,
                "description": exclusion.description,
                "source_form": base_form_data.form_id,
                "is_standard_provision": True,
                "is_modified": False,
                "form_section": exclusion.form_section,
            })

        # Calculate confidence
        all_confidences = (
            [c["confidence"] for c in effective_coverages] +
            [e["confidence"] for e in effective_exclusions]
        )
        overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        result = {
            "effective_coverages": effective_coverages,
            "effective_exclusions": effective_exclusions,
            "overall_confidence": overall_confidence,
            "synthesis_method": SynthesisMethod.TWO_DOCUMENT_MERGE.value,
            "source_endorsement_count": 0,
            "base_form_id": base_form_data.form_id,
            "fallback_recommended": False,
        }

        # Add descriptions
        result = self._add_descriptions(result)

        return result

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
                    "is_standard_provision": False,
                    "is_modified": False,
                })

        # Boost confidence with inference data
        if inferred:
            current_conf = synthesis_result.get("overall_confidence", 0.0)
            inference_conf = inference_result.get("confidence", 0.7)
            # Weighted average favoring the higher confidence
            synthesis_result["overall_confidence"] = max(current_conf, inference_conf * 0.9)

        return synthesis_result

    def _infer_coverage_type(self, coverage_name: str) -> Optional[str]:
        """Infer coverage type from name.

        Args:
            coverage_name: Coverage name.

        Returns:
            Coverage type or None.
        """
        name_lower = coverage_name.lower()

        if "auto" in name_lower or "vehicle" in name_lower:
            return "Auto"
        elif "liability" in name_lower:
            return "Liability"
        elif "property" in name_lower or "building" in name_lower or "physical damage" in name_lower:
            return "Property"
        elif "workers" in name_lower or "compensation" in name_lower:
            return "Workers Comp"
        else:
            return None

    def _get_inline_knowledge_base(self) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Get inline knowledge base for standard form provisions.

        This provides the standard provisions for common ISO forms without
        requiring imports from the extraction module (avoiding circular imports).

        Returns:
            Dict mapping form_id to provision data.
        """
        return {
            "CA 00 01": {
                "form_name": "Business Auto Coverage Form",
                "exclusions": [
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
                ],
                "coverages": [
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
                ],
                "conditions": [
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
                ],
            },
        }
