"""Coverage Synthesizer - transforms endorsement modifications into effective coverages.

This service implements the FurtherAI-style coverage-centric output by:
1. Grouping endorsement modifications by impacted coverage
2. Merging modifications to determine effective terms
3. Tracking source attribution for each term
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict

from app.schemas.product.synthesis_models import (
    EffectiveCoverage,
    EffectiveTerm,
    SynthesisResult,
    SynthesisMethod,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Mapping of effect categories to term status
EFFECT_TO_STATUS = {
    "adds_coverage": "Covered",
    "expands_coverage": "Expanded",
    "limits_coverage": "Restricted",
    "restores_coverage": "Restored",
}

# Mapping of endorsement_type to term status (for basic endorsement data)
ENDORSEMENT_TYPE_TO_STATUS = {
    "Add": "Added",
    "Modify": "Modified",
    "Restrict": "Restricted",
    "Delete": "Removed",
    "Expand": "Expanded",
}


class CoverageSynthesizer:
    """Synthesizes effective coverages from endorsement modifications.

    This service transforms endorsement-centric extraction output into
    coverage-centric output suitable for broker/underwriter consumption.
    """

    def __init__(self):
        """Initialize the coverage synthesizer."""
        self.logger = LOGGER

    def synthesize_coverages(
        self,
        endorsement_modifications: Optional[Dict[str, Any]] = None,
        endorsement_data: Optional[Dict[str, Any]] = None,
        base_coverages: Optional[List[Dict[str, Any]]] = None,
    ) -> SynthesisResult:
        """Synthesize effective coverages from endorsement data.

        Args:
            endorsement_modifications: Output from EndorsementCoverageProjectionExtractor
                Contains detailed modification data with effect categories.
            endorsement_data: Output from basic EndorsementsExtractor
                Contains endorsement_name, endorsement_type, impacted_coverage.
            base_coverages: Optional base coverage data from COVERAGES section extraction.

        Returns:
            SynthesisResult with effective_coverages populated.
        """
        # Collect all modifications grouped by coverage
        coverage_modifications: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        source_endorsements: Dict[str, set] = defaultdict(set)

        # Process detailed projection modifications (preferred source)
        if endorsement_modifications:
            self._process_projection_modifications(
                endorsement_modifications,
                coverage_modifications,
                source_endorsements,
            )

        # Process basic endorsement data as fallback
        if endorsement_data and not endorsement_modifications:
            self._process_basic_endorsements(
                endorsement_data,
                coverage_modifications,
                source_endorsements,
            )

        # Build effective coverages
        effective_coverages = self._build_effective_coverages(
            coverage_modifications,
            source_endorsements,
            base_coverages,
        )

        # Calculate overall confidence
        if effective_coverages:
            overall_confidence = sum(c.confidence for c in effective_coverages) / len(effective_coverages)
        else:
            overall_confidence = 0.0

        return SynthesisResult(
            effective_coverages=effective_coverages,
            effective_exclusions=[],  # Handled by ExclusionSynthesizer
            overall_confidence=overall_confidence,
            synthesis_method=SynthesisMethod.ENDORSEMENT_ONLY.value,
            source_endorsement_count=len(set().union(*source_endorsements.values())) if source_endorsements else 0,
        )

    def _process_projection_modifications(
        self,
        endorsement_modifications: Dict[str, Any],
        coverage_modifications: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
    ) -> None:
        """Process detailed endorsement projection modifications.

        Args:
            endorsement_modifications: The projection output with modifications list.
            coverage_modifications: Dict to populate with modifications by coverage.
            source_endorsements: Dict to populate with source endorsement references.
        """
        endorsements = endorsement_modifications.get("endorsements", [])

        for endorsement in endorsements:
            endorsement_ref = endorsement.get("endorsement_number") or endorsement.get("endorsement_name", "Unknown")
            modifications = endorsement.get("modifications", [])

            for mod in modifications:
                impacted_coverage = mod.get("impacted_coverage")
                if not impacted_coverage:
                    continue

                # Normalize coverage name
                coverage_key = self._normalize_coverage_name(impacted_coverage)

                coverage_modifications[coverage_key].append({
                    "effect": mod.get("coverage_effect"),
                    "effect_category": mod.get("effect_category"),
                    "scope_modification": mod.get("scope_modification"),
                    "limit_modification": mod.get("limit_modification"),
                    "deductible_modification": mod.get("deductible_modification"),
                    "condition_modification": mod.get("condition_modification"),
                    "verbatim_language": mod.get("verbatim_language"),
                    "source": endorsement_ref,
                })
                source_endorsements[coverage_key].add(endorsement_ref)

        # Also process flattened all_modifications if present
        all_mods = endorsement_modifications.get("all_modifications", [])
        for mod in all_mods:
            impacted_coverage = mod.get("impacted_coverage")
            if not impacted_coverage:
                continue

            coverage_key = self._normalize_coverage_name(impacted_coverage)
            source = mod.get("source_endorsement", "Unknown")

            # Avoid duplicates from endorsements list
            existing_sources = {m.get("source") for m in coverage_modifications[coverage_key]}
            if source not in existing_sources:
                coverage_modifications[coverage_key].append({
                    "effect": mod.get("coverage_effect"),
                    "effect_category": mod.get("effect_category"),
                    "scope_modification": mod.get("scope_modification"),
                    "limit_modification": mod.get("limit_modification"),
                    "condition_modification": mod.get("condition_modification"),
                    "source": source,
                })
                source_endorsements[coverage_key].add(source)

    def _process_basic_endorsements(
        self,
        endorsement_data: Dict[str, Any],
        coverage_modifications: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
    ) -> None:
        """Process basic endorsement extraction data.

        Args:
            endorsement_data: Basic endorsements extraction output.
            coverage_modifications: Dict to populate.
            source_endorsements: Dict to populate.
        """
        endorsements = endorsement_data.get("endorsements", [])

        for endorsement in endorsements:
            impacted_coverage = endorsement.get("impacted_coverage")
            if not impacted_coverage:
                continue

            endorsement_ref = endorsement.get("endorsement_number") or endorsement.get("endorsement_name", "Unknown")
            endorsement_type = endorsement.get("endorsement_type", "Modify")

            # Handle multi-coverage references (space-separated)
            coverage_names = self._split_coverage_references(impacted_coverage)

            for coverage_name in coverage_names:
                coverage_key = self._normalize_coverage_name(coverage_name)

                coverage_modifications[coverage_key].append({
                    "effect": endorsement_type,
                    "effect_category": self._infer_effect_category(endorsement_type),
                    "endorsement_name": endorsement.get("endorsement_name"),
                    "materiality": endorsement.get("materiality"),
                    "source": endorsement_ref,
                })
                source_endorsements[coverage_key].add(endorsement_ref)

    def _build_effective_coverages(
        self,
        coverage_modifications: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
        base_coverages: Optional[List[Dict[str, Any]]],
    ) -> List[EffectiveCoverage]:
        """Build EffectiveCoverage objects from grouped modifications.

        Args:
            coverage_modifications: Modifications grouped by coverage name.
            source_endorsements: Source endorsements by coverage name.
            base_coverages: Optional base coverage data.

        Returns:
            List of EffectiveCoverage objects.
        """
        effective_coverages = []

        for coverage_name, modifications in coverage_modifications.items():
            if not modifications:
                continue

            # Build effective terms from modifications
            effective_terms = {}
            detailed_terms = []
            limits = {}
            deductibles = {}

            for mod in modifications:
                effect_category = mod.get("effect_category", "")
                status = EFFECT_TO_STATUS.get(effect_category, mod.get("effect", "Modified"))

                # Build term from scope modification
                scope_mod = mod.get("scope_modification")
                if scope_mod:
                    term_key = self._extract_term_key(scope_mod)
                    effective_terms[term_key] = status

                    detailed_terms.append(EffectiveTerm(
                        term_name=term_key,
                        status=status,
                        details=scope_mod,
                        conditions=[mod.get("condition_modification")] if mod.get("condition_modification") else None,
                        source_endorsement=mod.get("source"),
                    ))

                # Track limit modifications
                limit_mod = mod.get("limit_modification")
                if limit_mod:
                    limits["limit_modification"] = limit_mod

                # Track deductible modifications
                ded_mod = mod.get("deductible_modification")
                if ded_mod:
                    deductibles["deductible_modification"] = ded_mod

                # For basic endorsements without scope, create generic term
                if not scope_mod and mod.get("endorsement_name"):
                    term_key = mod.get("endorsement_name", "General Coverage")
                    effective_terms[term_key] = ENDORSEMENT_TYPE_TO_STATUS.get(mod.get("effect"), "Modified")

            # Calculate confidence based on data quality
            confidence = self._calculate_confidence(modifications)

            effective_coverages.append(EffectiveCoverage(
                coverage_name=coverage_name,
                coverage_type=self._infer_coverage_type(coverage_name),
                effective_terms=effective_terms,
                detailed_terms=detailed_terms if detailed_terms else None,
                limits=limits if limits else None,
                deductibles=deductibles if deductibles else None,
                sources=list(source_endorsements.get(coverage_name, [])),
                confidence=confidence,
            ))

        return effective_coverages

    def _normalize_coverage_name(self, coverage_name: str) -> str:
        """Normalize coverage name for grouping.

        Args:
            coverage_name: Raw coverage name from extraction.

        Returns:
            Normalized coverage name.
        """
        # Remove common form suffixes
        name = coverage_name.strip()
        for suffix in [" COVERAGE FORM", " FORM", " COVERAGE"]:
            if name.upper().endswith(suffix):
                name = name[:-len(suffix)].strip()

        # Title case for consistency
        return name.title()

    def _split_coverage_references(self, impacted_coverage: str) -> List[str]:
        """Split multi-coverage references.

        Args:
            impacted_coverage: Possibly space-separated coverage list.

        Returns:
            List of individual coverage names.
        """
        # Common patterns like "AUTO DEALERS COVERAGE FORM BUSINESS AUTO COVERAGE FORM"
        # These are space-separated form names
        forms = []
        current = []

        for word in impacted_coverage.split():
            current.append(word)
            if word.upper() == "FORM":
                forms.append(" ".join(current))
                current = []

        if current:
            # Remaining words form one coverage
            if forms:
                # Append to last form if it looks like a continuation
                forms.append(" ".join(current))
            else:
                forms = [" ".join(current)]

        return forms if forms else [impacted_coverage]

    def _infer_effect_category(self, endorsement_type: str) -> str:
        """Infer effect category from basic endorsement type.

        Args:
            endorsement_type: Add | Modify | Restrict | Delete

        Returns:
            Effect category string.
        """
        mapping = {
            "Add": "adds_coverage",
            "Expand": "expands_coverage",
            "Modify": "expands_coverage",  # Assume positive unless stated
            "Restrict": "limits_coverage",
            "Delete": "limits_coverage",
        }
        return mapping.get(endorsement_type, "expands_coverage")

    def _extract_term_key(self, scope_modification: str) -> str:
        """Extract a term key from scope modification text.

        Args:
            scope_modification: Description of scope change.

        Returns:
            Short term key for the effective_terms dict.
        """
        # Look for key phrases
        scope_lower = scope_modification.lower()

        if "hired auto" in scope_lower:
            return "hired_auto"
        elif "non-owned" in scope_lower or "non owned" in scope_lower:
            return "non_owned_auto"
        elif "additional insured" in scope_lower:
            return "additional_insured"
        elif "supplementary" in scope_lower:
            return "supplementary_payments"
        elif "waiver" in scope_lower:
            return "waiver_of_subrogation"
        elif "primary" in scope_lower:
            return "primary_and_noncontributory"
        else:
            # Use first few words as key
            words = scope_modification.split()[:4]
            return "_".join(w.lower() for w in words)

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
        elif "property" in name_lower or "building" in name_lower:
            return "Property"
        elif "workers" in name_lower or "compensation" in name_lower:
            return "Workers Comp"
        else:
            return None

    def _calculate_confidence(self, modifications: List[Dict[str, Any]]) -> float:
        """Calculate confidence score for synthesized coverage.

        Args:
            modifications: List of modifications for this coverage.

        Returns:
            Confidence score 0.0-1.0.
        """
        if not modifications:
            return 0.0

        # Start with base confidence
        confidence = 0.7

        # Boost for detailed modifications
        detailed_count = sum(1 for m in modifications if m.get("scope_modification") or m.get("verbatim_language"))
        if detailed_count > 0:
            confidence += 0.1

        # Boost for multiple corroborating sources
        unique_sources = len(set(m.get("source", "") for m in modifications if m.get("source")))
        if unique_sources > 1:
            confidence += 0.05

        # Boost for effect category presence
        categorized = sum(1 for m in modifications if m.get("effect_category"))
        if categorized == len(modifications):
            confidence += 0.1

        return min(confidence, 0.98)
