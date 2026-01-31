"""Exclusion Synthesizer - transforms endorsement modifications into effective exclusions.

This service implements the FurtherAI-style exclusion-centric output by:
1. Grouping endorsement modifications by impacted exclusion
2. Determining effective state (Excluded, Partially Excluded, Carved Back, Removed)
3. Tracking carve-backs and conditions
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict

from app.schemas.product.synthesis_models import (
    EffectiveExclusion,
    SynthesisResult,
    SynthesisMethod,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Mapping of effect categories to effective state
EFFECT_TO_STATE = {
    "introduces_exclusion": "Excluded",
    "narrows_exclusion": "Partially Excluded",
    "removes_exclusion": "Removed",
}


class ExclusionSynthesizer:
    """Synthesizes effective exclusions from endorsement modifications.

    This service transforms endorsement-centric extraction output into
    exclusion-centric output suitable for broker/underwriter consumption.
    """

    def __init__(self):
        """Initialize the exclusion synthesizer."""
        self.logger = LOGGER

    def synthesize_exclusions(
        self,
        exclusion_modifications: Optional[Dict[str, Any]] = None,
        base_exclusions: Optional[List[Dict[str, Any]]] = None,
    ) -> SynthesisResult:
        """Synthesize effective exclusions from endorsement data.

        Args:
            exclusion_modifications: Output from EndorsementExclusionProjectionExtractor.
            base_exclusions: Optional base exclusion data from EXCLUSIONS section.

        Returns:
            SynthesisResult with effective_exclusions populated.
        """
        # Collect all modifications grouped by exclusion
        exclusion_mods: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        source_endorsements: Dict[str, set] = defaultdict(set)

        # Process exclusion projection modifications
        if exclusion_modifications:
            self._process_exclusion_modifications(
                exclusion_modifications,
                exclusion_mods,
                source_endorsements,
            )

        # Build effective exclusions
        effective_exclusions = self._build_effective_exclusions(
            exclusion_mods,
            source_endorsements,
            base_exclusions,
        )

        # Calculate overall confidence
        if effective_exclusions:
            overall_confidence = sum(e.confidence for e in effective_exclusions) / len(effective_exclusions)
        else:
            overall_confidence = 0.0

        return SynthesisResult(
            effective_coverages=[],  # Handled by CoverageSynthesizer
            effective_exclusions=effective_exclusions,
            overall_confidence=overall_confidence,
            synthesis_method=SynthesisMethod.ENDORSEMENT_ONLY.value,
            source_endorsement_count=len(set().union(*source_endorsements.values())) if source_endorsements else 0,
        )

    def _process_exclusion_modifications(
        self,
        exclusion_modifications: Dict[str, Any],
        exclusion_mods: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
    ) -> None:
        """Process exclusion projection modifications.

        Args:
            exclusion_modifications: The projection output with modifications list.
            exclusion_mods: Dict to populate with modifications by exclusion.
            source_endorsements: Dict to populate with source endorsement references.
        """
        endorsements = exclusion_modifications.get("endorsements", [])

        for endorsement in endorsements:
            endorsement_ref = endorsement.get("endorsement_number") or endorsement.get("endorsement_name", "Unknown")
            modifications = endorsement.get("modifications", [])

            for mod in modifications:
                impacted_exclusion = mod.get("impacted_exclusion")
                if not impacted_exclusion:
                    continue

                # Normalize exclusion name
                exclusion_key = self._normalize_exclusion_name(impacted_exclusion)

                exclusion_mods[exclusion_key].append({
                    "effect": mod.get("exclusion_effect"),
                    "effect_category": mod.get("effect_category"),
                    "exclusion_scope": mod.get("exclusion_scope"),
                    "impacted_coverage": mod.get("impacted_coverage"),
                    "exception_conditions": mod.get("exception_conditions"),
                    "verbatim_language": mod.get("verbatim_language"),
                    "severity": mod.get("severity"),
                    "source": endorsement_ref,
                })
                source_endorsements[exclusion_key].add(endorsement_ref)

    def _build_effective_exclusions(
        self,
        exclusion_mods: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
        base_exclusions: Optional[List[Dict[str, Any]]],
    ) -> List[EffectiveExclusion]:
        """Build EffectiveExclusion objects from grouped modifications.

        Args:
            exclusion_mods: Modifications grouped by exclusion name.
            source_endorsements: Source endorsements by exclusion name.
            base_exclusions: Optional base exclusion data.

        Returns:
            List of EffectiveExclusion objects.
        """
        effective_exclusions = []

        for exclusion_name, modifications in exclusion_mods.items():
            if not modifications:
                continue

            # Determine effective state from modifications
            effective_state = self._determine_effective_state(modifications)

            # Collect carve-backs (conditions that restore coverage)
            carve_backs = []
            conditions = []
            impacted_coverages = set()
            severity = None

            for mod in modifications:
                # Carve-backs come from narrowing exclusions
                if mod.get("effect_category") == "narrows_exclusion":
                    exception = mod.get("exception_conditions")
                    if exception:
                        carve_backs.append(exception)

                # General conditions
                if mod.get("exception_conditions") and mod.get("effect_category") != "narrows_exclusion":
                    conditions.append(mod.get("exception_conditions"))

                # Track impacted coverages
                if mod.get("impacted_coverage"):
                    impacted_coverages.add(mod.get("impacted_coverage"))

                # Track severity (use highest)
                mod_severity = mod.get("severity")
                if mod_severity:
                    if severity is None or self._severity_rank(mod_severity) > self._severity_rank(severity):
                        severity = mod_severity

            # Calculate confidence
            confidence = self._calculate_confidence(modifications)

            # Get scope from first modification that has it
            scope = None
            for mod in modifications:
                if mod.get("exclusion_scope"):
                    scope = mod.get("exclusion_scope")
                    break

            effective_exclusions.append(EffectiveExclusion(
                exclusion_name=exclusion_name,
                effective_state=effective_state,
                scope=scope,
                carve_backs=carve_backs if carve_backs else None,
                conditions=conditions if conditions else None,
                impacted_coverages=list(impacted_coverages) if impacted_coverages else None,
                sources=list(source_endorsements.get(exclusion_name, [])),
                confidence=confidence,
                severity=severity,
            ))

        return effective_exclusions

    def _normalize_exclusion_name(self, exclusion_name: str) -> str:
        """Normalize exclusion name for grouping.

        Args:
            exclusion_name: Raw exclusion name.

        Returns:
            Normalized exclusion name.
        """
        return exclusion_name.strip().title()

    def _determine_effective_state(self, modifications: List[Dict[str, Any]]) -> str:
        """Determine effective exclusion state from modifications.

        Args:
            modifications: List of modifications for this exclusion.

        Returns:
            Effective state string.
        """
        # Check for removal first (strongest)
        for mod in modifications:
            if mod.get("effect_category") == "removes_exclusion":
                return "Removed"

        # Check for narrowing (partial exclusion)
        has_narrowing = any(mod.get("effect_category") == "narrows_exclusion" for mod in modifications)
        has_introduction = any(mod.get("effect_category") == "introduces_exclusion" for mod in modifications)

        if has_narrowing:
            return "Partially Excluded"
        elif has_introduction:
            return "Excluded"
        else:
            # Default based on effect type
            effects = [mod.get("effect", "").lower() for mod in modifications]
            if "narrow" in effects or "delete" in effects:
                return "Partially Excluded"
            return "Excluded"

    def _severity_rank(self, severity: str) -> int:
        """Get numeric rank for severity comparison.

        Args:
            severity: Severity string.

        Returns:
            Numeric rank (higher = more severe).
        """
        ranks = {
            "Material": 3,
            "Minor": 2,
            "Administrative": 1,
        }
        return ranks.get(severity, 0)

    def _calculate_confidence(self, modifications: List[Dict[str, Any]]) -> float:
        """Calculate confidence score for synthesized exclusion.

        Args:
            modifications: List of modifications for this exclusion.

        Returns:
            Confidence score 0.0-1.0.
        """
        if not modifications:
            return 0.0

        confidence = 0.7

        # Boost for detailed modifications
        detailed_count = sum(1 for m in modifications if m.get("exclusion_scope") or m.get("verbatim_language"))
        if detailed_count > 0:
            confidence += 0.1

        # Boost for severity information
        has_severity = any(m.get("severity") for m in modifications)
        if has_severity:
            confidence += 0.05

        # Boost for effect category presence
        categorized = sum(1 for m in modifications if m.get("effect_category"))
        if categorized == len(modifications):
            confidence += 0.1

        return min(confidence, 0.98)
