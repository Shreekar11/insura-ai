"""Exclusion Synthesizer - transforms endorsement modifications into effective exclusions.

This service implements the exclusion-centric output by:
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
        endorsement_data: Optional[Dict[str, Any]] = None,
        base_exclusions: Optional[List[Dict[str, Any]]] = None,
    ) -> SynthesisResult:
        """Synthesize effective exclusions from endorsement data.

        Args:
            exclusion_modifications: Output from EndorsementExclusionProjectionExtractor.
            endorsement_data: Output from basic EndorsementsExtractor.
                Contains endorsement_name, endorsement_type, impacted_coverage.
                Used as fallback when exclusion_modifications is not available.
            base_exclusions: Optional base exclusion data from EXCLUSIONS section.

        Returns:
            SynthesisResult with effective_exclusions populated.
        """
        # Collect all modifications grouped by exclusion
        exclusion_mods: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        source_endorsements: Dict[str, set] = defaultdict(set)

        # Process exclusion projection modifications (preferred source)
        if exclusion_modifications:
            self._process_exclusion_modifications(
                exclusion_modifications,
                exclusion_mods,
                source_endorsements,
            )

        # Process basic endorsement data as fallback
        # This extracts exclusion effects from endorsements with restrictive types
        if endorsement_data and not exclusion_modifications:
            self._process_basic_endorsements(
                endorsement_data,
                exclusion_mods,
                source_endorsements,
            )

        # Determine synthesis method based on available data
        has_endorsements = bool(exclusion_modifications or endorsement_data)
        has_base_exclusions = bool(base_exclusions)

        # Build effective exclusions
        if has_endorsements:
            # Build from endorsement modifications
            effective_exclusions = self._build_effective_exclusions(
                exclusion_mods,
                source_endorsements,
                base_exclusions,
            )
            synthesis_method = SynthesisMethod.ENDORSEMENT_ONLY.value
        elif has_base_exclusions:
            # Convert base exclusions directly to effective exclusions (no endorsements)
            effective_exclusions = self._convert_base_to_effective_exclusions(base_exclusions)
            synthesis_method = SynthesisMethod.BASE_COVERAGE_MERGE.value
            self.logger.info(
                f"No endorsements found. Converting {len(base_exclusions)} base exclusions to effective exclusions."
            )
        else:
            effective_exclusions = []
            synthesis_method = SynthesisMethod.ENDORSEMENT_ONLY.value

        # Calculate overall confidence
        if effective_exclusions:
            overall_confidence = sum(e.confidence for e in effective_exclusions) / len(effective_exclusions)
        else:
            overall_confidence = 0.0

        return SynthesisResult(
            effective_coverages=[],  # Handled by CoverageSynthesizer
            effective_exclusions=effective_exclusions,
            overall_confidence=overall_confidence,
            synthesis_method=synthesis_method,
            source_endorsement_count=len(set().union(*source_endorsements.values())) if source_endorsements else 0,
        )

    def _convert_base_to_effective_exclusions(
        self,
        base_exclusions: List[Dict[str, Any]],
    ) -> List[EffectiveExclusion]:
        """Convert base exclusion data directly to EffectiveExclusion objects.

        This method is used when there are no endorsement modifications,
        making the base exclusions the effective exclusions.

        Args:
            base_exclusions: Base exclusion data from EXCLUSIONS section extraction.

        Returns:
            List of EffectiveExclusion objects.
        """
        effective_exclusions = []

        for exclusion in base_exclusions:
            # Extract exclusion name from various possible field names
            exclusion_name = (
                exclusion.get("exclusion_name") or
                exclusion.get("title") or
                exclusion.get("name") or
                "Unknown Exclusion"
            )

            # Extract description
            description = exclusion.get("description") or exclusion.get("summary")

            # Extract scope
            scope = exclusion.get("exclusion_scope") or exclusion.get("scope")

            # Extract impacted coverages
            impacted_coverages = None
            if exclusion.get("impacted_coverage"):
                impacted_coverages = [exclusion.get("impacted_coverage")]
            elif exclusion.get("impacted_coverages"):
                impacted_coverages = exclusion.get("impacted_coverages")

            # Extract exceptions/carve-backs
            carve_backs = None
            if exclusion.get("exceptions"):
                exceptions = exclusion.get("exceptions")
                if isinstance(exceptions, str):
                    carve_backs = [exceptions]
                elif isinstance(exceptions, list):
                    carve_backs = exceptions

            # Get severity
            severity = exclusion.get("severity", "Material")

            # Get confidence from entity or default
            confidence = exclusion.get("confidence", 0.95)

            # Get exclusion number/reference
            exclusion_number = (
                exclusion.get("exclusion_number") or
                exclusion.get("reference") or
                exclusion.get("provision_number")
            )

            effective_exclusions.append(EffectiveExclusion(
                exclusion_name=exclusion_name,
                effective_state="Excluded",  # Base exclusions are in effect
                scope=scope,
                carve_backs=carve_backs,
                conditions=None,
                impacted_coverages=impacted_coverages,
                sources=["Base Form"],
                confidence=confidence,
                severity=severity,
                exclusion_number=exclusion_number,
                description=description,
                source_form=exclusion.get("source_form"),
                is_standard_provision=True,
                is_modified=False,
                form_section=exclusion.get("form_section"),
            ))

        return effective_exclusions

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

    def _process_basic_endorsements(
        self,
        endorsement_data: Dict[str, Any],
        exclusion_mods: Dict[str, List[Dict[str, Any]]],
        source_endorsements: Dict[str, set],
    ) -> None:
        """Process basic endorsement extraction data for exclusion effects.

        This method extracts exclusion-related information from endorsements
        that have restrictive effects (type = "Restrict", "Delete") or
        endorsement names that suggest exclusion modifications (e.g., "waiver").

        Args:
            endorsement_data: Basic endorsements extraction output.
            exclusion_mods: Dict to populate with exclusion modifications.
            source_endorsements: Dict to populate with source endorsement references.
        """
        endorsements = endorsement_data.get("endorsements", [])

        # Enhanced keywords for exclusion-related modifications
        # Primary keywords that strongly indicate exclusion modifications
        primary_exclusion_keywords = [
            "waiver", "subrogation", "exclusion", "limitation",
            "restriction", "carve", "delete", "remove", "narrow",
            "transfer of rights", "recovery against others",
        ]

        # Secondary keywords that may indicate exclusion modifications
        secondary_exclusion_keywords = [
            "except", "unless", "provided that", "subject to",
            "applicable to", "does not apply", "not covered",
            "prohibited", "void", "suspended", "limited to",
        ]

        # Double-negative patterns that narrow/remove exclusions
        # These phrases often indicate the exclusion is being carved back
        narrowing_patterns = [
            "does not apply to",
            "shall not apply",
            "exclusion does not apply",
            "not applicable to",
            "is not excluded",
            "exception to exclusion",
        ]

        for endorsement in endorsements:
            endorsement_name = endorsement.get("endorsement_name", "")
            endorsement_type = endorsement.get("endorsement_type", "")
            endorsement_ref = (
                endorsement.get("endorsement_number") or
                endorsement_name or
                "Unknown"
            )
            impacted_coverage = endorsement.get("impacted_coverage")
            materiality = endorsement.get("materiality")

            # Determine if this endorsement affects exclusions
            name_lower = endorsement_name.lower()

            # Check for primary keywords
            has_primary_keyword = any(
                keyword in name_lower for keyword in primary_exclusion_keywords
            )

            # Check for secondary keywords
            has_secondary_keyword = any(
                keyword in name_lower for keyword in secondary_exclusion_keywords
            )

            # Check for restrictive endorsement types
            is_restrictive_type = endorsement_type in ("Restrict", "Delete")

            # Check for double-negative patterns
            has_narrowing_pattern = any(
                pattern in name_lower for pattern in narrowing_patterns
            )

            # Determine if exclusion-related
            is_exclusion_related = (
                has_primary_keyword or
                is_restrictive_type or
                (has_secondary_keyword and endorsement_type in ("Modify", "Restrict"))
            )

            if not is_exclusion_related:
                continue

            # Determine effect category based on endorsement type, name, and patterns
            effect_category = self._infer_exclusion_effect_category(
                endorsement_type, endorsement_name, has_narrowing_pattern
            )

            # Infer severity from materiality or endorsement characteristics
            severity = self._infer_severity(materiality, endorsement_type, name_lower)

            # Generate exclusion name based on endorsement
            exclusion_name = self._generate_exclusion_name(
                endorsement_name, impacted_coverage
            )
            exclusion_key = self._normalize_exclusion_name(exclusion_name)

            # Extract any condition hints from the endorsement name
            condition_hints = self._extract_condition_hints(name_lower)

            exclusion_mods[exclusion_key].append({
                "effect": endorsement_type,
                "effect_category": effect_category,
                "exclusion_scope": None,
                "impacted_coverage": impacted_coverage,
                "endorsement_name": endorsement_name,
                "materiality": materiality,
                "severity": severity,
                "source": endorsement_ref,
                "exception_conditions": condition_hints,
            })
            source_endorsements[exclusion_key].add(endorsement_ref)

        if exclusion_mods:
            self.logger.info(
                f"Processed {len(exclusion_mods)} exclusion-related endorsements "
                f"from basic endorsement data"
            )

    def _infer_severity(
        self, materiality: Optional[str], endorsement_type: str, name_lower: str
    ) -> str:
        """Infer severity from materiality, endorsement type, and name.

        Args:
            materiality: The materiality field from endorsement.
            endorsement_type: Endorsement type (Add, Modify, Restrict, Delete).
            name_lower: Lowercase endorsement name.

        Returns:
            Severity string (Critical, Major, Material, Minor).
        """
        # Use materiality if available
        if materiality:
            materiality_lower = materiality.lower()
            if materiality_lower in ("high", "critical"):
                return "Critical"
            elif materiality_lower == "medium":
                return "Major"
            elif materiality_lower == "low":
                return "Minor"

        # Infer from endorsement characteristics
        # Restrictive changes that affect liability are typically more severe
        if endorsement_type in ("Restrict", "Delete"):
            if any(term in name_lower for term in ["liability", "bodily injury", "property damage"]):
                return "Critical"
            return "Major"

        # Waivers that affect subrogation are typically material
        if "waiver" in name_lower or "subrogation" in name_lower:
            return "Material"

        # Default to Material
        return "Material"

    def _extract_condition_hints(self, name_lower: str) -> Optional[str]:
        """Extract condition hints from endorsement name.

        Args:
            name_lower: Lowercase endorsement name.

        Returns:
            Condition hint string or None.
        """
        # Look for conditional phrases
        conditional_patterns = [
            ("required by contract", "When required by written contract"),
            ("written contract", "Subject to written contract requirement"),
            ("scheduled", "For scheduled parties only"),
            ("blanket", "Blanket coverage for all qualifying parties"),
            ("designated", "For designated parties only"),
            ("per project", "Applied on a per-project basis"),
            ("per location", "Applied on a per-location basis"),
        ]

        for pattern, description in conditional_patterns:
            if pattern in name_lower:
                return description

        return None

    def _infer_exclusion_effect_category(
        self,
        endorsement_type: str,
        endorsement_name: str,
        has_narrowing_pattern: bool = False,
    ) -> str:
        """Infer exclusion effect category from endorsement data.

        Args:
            endorsement_type: Endorsement type (Add, Modify, Restrict, Delete).
            endorsement_name: Endorsement name.
            has_narrowing_pattern: Whether the name contains double-negative patterns.

        Returns:
            Effect category string.
        """
        name_lower = endorsement_name.lower()

        # Double-negative patterns strongly indicate narrowing
        # e.g., "does not apply to" means the exclusion is being carved back
        if has_narrowing_pattern:
            return "narrows_exclusion"

        # Waivers typically narrow/remove exclusions
        # Waiver of subrogation = insurer waives right to recover from third parties
        if "waiver" in name_lower:
            return "narrows_exclusion"

        # Transfer of rights waivers narrow subrogation exclusions
        if "transfer of rights" in name_lower or "recovery against others" in name_lower:
            return "narrows_exclusion"

        # Carve-backs and exceptions narrow exclusions
        if any(term in name_lower for term in ["carve", "except", "exception"]):
            return "narrows_exclusion"

        # "Does not apply" phrases indicate narrowing (exclusion doesn't apply)
        if "does not apply" in name_lower or "shall not apply" in name_lower:
            return "narrows_exclusion"

        # "Not excluded" or similar phrases indicate removal of exclusion
        if "not excluded" in name_lower or "is covered" in name_lower:
            return "removes_exclusion"

        # Deletions remove exclusions entirely
        if endorsement_type == "Delete" or "delete" in name_lower or "remove" in name_lower:
            return "removes_exclusion"

        # Extension endorsements often narrow exclusions to expand coverage
        if "extension" in name_lower and endorsement_type == "Add":
            return "narrows_exclusion"

        # Restrictions introduce or strengthen exclusions
        if endorsement_type == "Restrict":
            return "introduces_exclusion"

        # Limitation endorsements typically introduce new exclusions
        if "limitation" in name_lower or "limit" in name_lower:
            return "introduces_exclusion"

        # Prohibited or void language introduces exclusions
        if "prohibited" in name_lower or "void" in name_lower:
            return "introduces_exclusion"

        # Default to introducing exclusion for unrecognized patterns
        return "introduces_exclusion"

    def _generate_exclusion_name(
        self, endorsement_name: str, impacted_coverage: Optional[str]
    ) -> str:
        """Generate exclusion name from endorsement information.

        Args:
            endorsement_name: Endorsement name.
            impacted_coverage: Coverage affected by the endorsement.

        Returns:
            Generated exclusion name.
        """
        name_lower = endorsement_name.lower()

        # Map common endorsement patterns to standard exclusion names
        exclusion_name_patterns = [
            # Subrogation/Transfer of Rights patterns
            (["waiver", "subrogation"], "Waiver of Subrogation"),
            (["transfer of rights", "recovery against others"], "Transfer of Rights of Recovery Against Others"),
            (["waiver of right to recover"], "Waiver of Right to Recover"),

            # Additional Insured patterns
            (["additional insured", "blanket"], "Additional Insured Coverage"),
            (["additional insured", "primary"], "Additional Insured - Primary & Non-Contributory"),

            # Notice patterns
            (["notice of cancellation"], "Notice of Cancellation"),
            (["material change"], "Material Change Notice"),

            # Auto coverage patterns
            (["hired auto"], "Hired Auto Coverage"),
            (["non-owned auto"], "Non-Owned Auto Coverage"),
            (["short term hired"], "Short Term Hired Auto"),

            # Workers Comp patterns
            (["alternate employer"], "Alternate Employer Coverage"),
            (["voluntary compensation"], "Voluntary Compensation"),
        ]

        # Check for pattern matches
        for patterns, standard_name in exclusion_name_patterns:
            if all(pattern in name_lower for pattern in patterns):
                if impacted_coverage:
                    return f"{standard_name} - {impacted_coverage}"
                return standard_name

        # If endorsement name contains "exclusion", extract or use it directly
        if "exclusion" in name_lower:
            return endorsement_name

        # If endorsement name contains "waiver", standardize it
        if "waiver" in name_lower:
            clean_name = endorsement_name.replace("ENDORSEMENT", "").strip()
            if impacted_coverage:
                return f"{clean_name} - {impacted_coverage}"
            return clean_name

        # For extension endorsements, name based on what's being extended
        if "extension" in name_lower:
            clean_name = endorsement_name.replace("Extension", "Coverage Extension").replace("EXTENSION", "Coverage Extension")
            return clean_name

        # Generate name from coverage + endorsement context
        if impacted_coverage:
            return f"{impacted_coverage} - {endorsement_name}"

        return endorsement_name

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
            verbatim_fragments = []

            for mod in modifications:
                # Carve-backs come from narrowing exclusions
                if mod.get("effect_category") == "narrows_exclusion":
                    exception = mod.get("exception_conditions")
                    if exception:
                        carve_backs.append(exception)
                    # If no exception_conditions, generate from endorsement name
                    elif mod.get("endorsement_name"):
                        carve_back_desc = self._generate_carve_back_description(
                            mod.get("endorsement_name"),
                            mod.get("impacted_coverage"),
                        )
                        if carve_back_desc:
                            carve_backs.append(carve_back_desc)

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

                # Collect verbatim language for description
                if mod.get("verbatim_language"):
                    verbatim_fragments.append(mod.get("verbatim_language"))

            # Calculate confidence
            confidence = self._calculate_confidence(modifications)

            # Get scope from first modification that has it
            scope = None
            for mod in modifications:
                if mod.get("exclusion_scope"):
                    scope = mod.get("exclusion_scope")
                    break

            # Generate description from state and modifications
            description = self._generate_exclusion_description(
                exclusion_name,
                effective_state,
                modifications,
                verbatim_fragments,
            )

            # Deduplicate carve-backs
            unique_carve_backs = list(dict.fromkeys(carve_backs)) if carve_backs else None

            effective_exclusions.append(EffectiveExclusion(
                exclusion_name=exclusion_name,
                effective_state=effective_state,
                scope=scope,
                carve_backs=unique_carve_backs,
                conditions=conditions if conditions else None,
                impacted_coverages=list(impacted_coverages) if impacted_coverages else None,
                sources=list(source_endorsements.get(exclusion_name, [])),
                confidence=confidence,
                severity=severity,
                description=description,
                is_modified=True,  # These are all from endorsement modifications
                is_standard_provision=False,
            ))

        return effective_exclusions

    def _generate_carve_back_description(
        self, endorsement_name: str, impacted_coverage: Optional[str]
    ) -> Optional[str]:
        """Generate carve-back description from endorsement information.

        Args:
            endorsement_name: Endorsement name.
            impacted_coverage: Coverage affected by the endorsement.

        Returns:
            Carve-back description or None.
        """
        name_lower = endorsement_name.lower()

        # Common carve-back patterns
        if "waiver" in name_lower and "subrogation" in name_lower:
            if impacted_coverage:
                return f"Waiver of subrogation rights for {impacted_coverage} when required by written contract"
            return "Waiver of subrogation rights when required by written contract"

        if "transfer of rights" in name_lower:
            return "Transfer of recovery rights waived for designated parties"

        if "additional insured" in name_lower:
            if "blanket" in name_lower:
                return "Blanket additional insured status for parties required by written contract"
            return "Additional insured status granted per endorsement terms"

        if "primary" in name_lower and "non-contributory" in name_lower:
            return "Coverage is primary and non-contributory when required by written contract"

        if "hired auto" in name_lower:
            return "Coverage extended to hired autos per endorsement terms"

        return None

    def _generate_exclusion_description(
        self,
        exclusion_name: str,
        effective_state: str,
        modifications: List[Dict[str, Any]],
        verbatim_fragments: List[str],
    ) -> str:
        """Generate human-readable description for the effective exclusion.

        Args:
            exclusion_name: The exclusion name.
            effective_state: The effective state (Excluded, Partially Excluded, Removed).
            modifications: List of modifications for this exclusion.
            verbatim_fragments: Verbatim language from endorsements.

        Returns:
            Human-readable description.
        """
        # If we have verbatim language, use the first fragment
        if verbatim_fragments:
            return verbatim_fragments[0][:500]  # Limit length

        # Generate based on state and modifications
        if effective_state == "Removed":
            return f"{exclusion_name} has been removed by endorsement."

        if effective_state == "Partially Excluded":
            # Get the first narrowing modification's source
            for mod in modifications:
                if mod.get("effect_category") == "narrows_exclusion":
                    source = mod.get("source", "endorsement")
                    return f"{exclusion_name} has been narrowed by {source}, with exceptions that restore coverage."
            return f"{exclusion_name} has been partially carved back by endorsement modifications."

        # Default for Excluded state
        return f"{exclusion_name} applies as modified by endorsements."

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
            "Critical": 5,
            "Major": 4,
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
