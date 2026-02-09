"""Description Generator - creates human-readable descriptions for provisions.

This service generates clear, broker/underwriter-friendly descriptions for
coverages and exclusions. It uses:
1. Template-based generation for standard provisions
2. LLM fallback for complex or non-standard provisions
3. Modification summarization for endorsement effects
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Template descriptions for standard CA 00 01 exclusions
STANDARD_EXCLUSION_TEMPLATES = {
    "Expected Or Intended Injury": {
        "template": "No coverage for {scope} expected or intended from the standpoint of the insured.",
        "default_scope": "bodily injury or property damage",
        "severity": "Material",
        "broker_note": "Standard intentional act exclusion - cannot be endorsed around.",
    },
    "Contractual": {
        "template": "No coverage for liability assumed under {contract_type}, except for specific permitted contracts.",
        "default_scope": "any contract or agreement",
        "severity": "Material",
        "broker_note": "Review insured contract definition for exceptions.",
    },
    "Workers' Compensation": {
        "template": "No coverage for obligations under workers' compensation, disability benefits, or similar laws.",
        "default_scope": "employee injury claims",
        "severity": "Material",
        "broker_note": "Standard WC exclusion - ensure WC policy is in place.",
    },
    "Employee Indemnification And Employer's Liability": {
        "template": "No coverage for bodily injury to employees arising out of employment.",
        "default_scope": "employee injuries during employment",
        "severity": "Material",
        "broker_note": "Employers liability coverage needed for employee injury claims.",
    },
    "Fellow Employee": {
        "template": "No coverage for bodily injury to fellow employees of the insured.",
        "default_scope": "co-worker injuries",
        "severity": "Minor",
        "broker_note": "Can be deleted by endorsement if needed.",
    },
    "Care, Custody Or Control": {
        "template": "No coverage for damage to property owned, transported, or in the insured's care, custody or control.",
        "default_scope": "property in insured's possession",
        "severity": "Material",
        "broker_note": "Consider motor truck cargo coverage if transporting goods.",
    },
    "Handling Of Property": {
        "template": "No coverage for injury or damage from handling property before it is moved onto or after it is moved from a covered auto.",
        "default_scope": "loading/unloading operations",
        "severity": "Minor",
        "broker_note": "Loading/unloading typically covered by CGL.",
    },
    "Movement Of Property By Mechanical Device": {
        "template": "No coverage for injury or damage from movement of property by mechanical device not attached to the covered auto.",
        "default_scope": "external mechanical equipment",
        "severity": "Minor",
        "broker_note": "Forklifts and similar equipment excluded - need separate coverage.",
    },
    "Operations": {
        "template": "No coverage for injury or damage arising from operation of {equipment_type}.",
        "default_scope": "mobile equipment operations",
        "severity": "Material",
        "broker_note": "Mobile equipment liability typically covered by CGL.",
    },
    "Completed Operations": {
        "template": "No coverage for injury or damage arising from work after it has been completed or abandoned.",
        "default_scope": "completed work",
        "severity": "Material",
        "broker_note": "Completed operations exposure typically covered by CGL.",
    },
    "Pollution": {
        "template": "No coverage for injury or damage arising from pollution, with limited exceptions for covered pollution costs.",
        "default_scope": "environmental contamination",
        "severity": "Material",
        "broker_note": "Review pollution exclusion carefully - limited carve-back for auto accidents.",
    },
    "War": {
        "template": "No coverage for injury or damage arising from war, insurrection, rebellion, or revolution.",
        "default_scope": "war-related events",
        "severity": "Material",
        "broker_note": "Standard war exclusion - typically uninsurable.",
    },
    "Racing": {
        "template": "No coverage while covered auto is used in any professional or organized racing or demolition contest.",
        "default_scope": "racing activities",
        "severity": "Material",
        "broker_note": "Absolute exclusion for racing activities.",
    },
}

# Template descriptions for standard CA 00 01 coverages
STANDARD_COVERAGE_TEMPLATES = {
    "Covered Autos Liability Coverage": {
        "template": "Pays all sums the insured legally must pay as damages for {damages_type} caused by an accident resulting from ownership, maintenance, or use of a covered auto.",
        "default_damages": "bodily injury or property damage",
        "key_features": [
            "Defense costs included",
            "Supplementary payments for bonds and expenses",
            "Duty to defend all suits",
        ],
    },
    "Physical Damage Coverage - Comprehensive": {
        "template": "Covers loss to a covered auto from any cause except collision, including theft, vandalism, fire, and weather damage.",
        "key_features": [
            "Broad form coverage",
            "Excludes collision/overturn",
            "Glass breakage option",
        ],
    },
    "Physical Damage Coverage - Collision": {
        "template": "Covers loss to a covered auto caused by collision with another object or by overturn.",
        "key_features": [
            "Requires deductible",
            "Covers rollover damage",
            "Actual cash value settlement",
        ],
    },
    "Physical Damage Coverage - Specified Causes of Loss": {
        "template": "Covers loss to a covered auto only from specified causes: fire, lightning, explosion, theft, windstorm, hail, earthquake, flood, mischief, vandalism, or sinking of a vessel.",
        "key_features": [
            "Named perils only",
            "Lower premium than comprehensive",
            "Good for older vehicles",
        ],
    },
    "Towing": {
        "template": "Covers towing and labor costs when a covered auto is disabled, subject to the limit shown in the declarations.",
        "key_features": [
            "Per-disablement limit",
            "Labor at disablement site only",
            "Does not cover repair costs",
        ],
    },
}


@dataclass
class DescriptionContext:
    """Context for generating descriptions."""
    provision_name: str
    provision_type: str  # "coverage" or "exclusion"
    source_form: Optional[str] = None
    modification_type: Optional[str] = None  # "expanded", "restricted", "removed"
    endorsement_source: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


class DescriptionGenerator:
    """Generates human-readable descriptions for insurance provisions.

    This service creates clear, consistent descriptions for coverages and
    exclusions, suitable for broker reports and underwriting summaries.

    Attributes:
        exclusion_templates: Templates for standard exclusion descriptions.
        coverage_templates: Templates for standard coverage descriptions.
        llm_client: Optional LLM client for complex descriptions.
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
    ):
        """Initialize the description generator.

        Args:
            llm_client: Optional UnifiedLLMClient for complex descriptions.
        """
        self.exclusion_templates = STANDARD_EXCLUSION_TEMPLATES
        self.coverage_templates = STANDARD_COVERAGE_TEMPLATES
        self.llm_client = llm_client
        self.logger = LOGGER

    def generate_exclusion_description(
        self,
        exclusion_name: str,
        context: Optional[DescriptionContext] = None,
        is_modified: bool = False,
        modification_details: Optional[str] = None,
    ) -> str:
        """Generate description for an exclusion.

        Args:
            exclusion_name: Name of the exclusion.
            context: Optional context for customization.
            is_modified: Whether the exclusion has been modified.
            modification_details: Details of modification if modified.

        Returns:
            Human-readable description string.
        """
        # Check for template match
        template_data = self._find_template_match(
            exclusion_name,
            self.exclusion_templates
        )

        if template_data:
            base_description = self._apply_template(
                template_data["template"],
                template_data,
                context
            )
        else:
            # Generic description for unknown exclusions
            base_description = f"This insurance does not apply to {exclusion_name.lower()}-related claims."

        # Add modification details if applicable
        if is_modified and modification_details:
            base_description = self._add_modification_suffix(
                base_description,
                modification_details,
                context
            )

        return base_description

    def generate_coverage_description(
        self,
        coverage_name: str,
        context: Optional[DescriptionContext] = None,
        is_modified: bool = False,
        modification_details: Optional[str] = None,
    ) -> str:
        """Generate description for a coverage.

        Args:
            coverage_name: Name of the coverage.
            context: Optional context for customization.
            is_modified: Whether the coverage has been modified.
            modification_details: Details of modification if modified.

        Returns:
            Human-readable description string.
        """
        # Check for template match
        template_data = self._find_template_match(
            coverage_name,
            self.coverage_templates
        )

        if template_data:
            base_description = self._apply_template(
                template_data["template"],
                template_data,
                context
            )
        else:
            # Generic description for unknown coverages
            base_description = f"Provides coverage for {coverage_name.lower()}-related losses as defined in the policy."

        # Add modification details if applicable
        if is_modified and modification_details:
            base_description = self._add_modification_suffix(
                base_description,
                modification_details,
                context
            )

        return base_description

    def generate_modification_summary(
        self,
        original_provision: str,
        modification_type: str,
        endorsement_number: Optional[str] = None,
        scope_change: Optional[str] = None,
        limit_change: Optional[str] = None,
    ) -> str:
        """Generate summary of how a provision was modified.

        Args:
            original_provision: Name of the original provision.
            modification_type: Type of modification (expand, restrict, remove, etc.).
            endorsement_number: The endorsement that made the change.
            scope_change: Description of scope changes.
            limit_change: Description of limit changes.

        Returns:
            Human-readable modification summary.
        """
        parts = []

        # Start with modification type
        mod_type_phrases = {
            "expand": "expanded by",
            "expands_coverage": "expanded by",
            "restrict": "restricted by",
            "limits_coverage": "restricted by",
            "remove": "removed by",
            "removes_exclusion": "removed by",
            "add": "added by",
            "adds_coverage": "added by",
            "narrow": "narrowed by",
            "narrows_exclusion": "partially restored by",
            "restore": "restored by",
            "restores_coverage": "restored by",
        }

        mod_phrase = mod_type_phrases.get(
            modification_type.lower(),
            f"modified by"
        )

        if endorsement_number:
            parts.append(f"{original_provision} {mod_phrase} endorsement {endorsement_number}")
        else:
            parts.append(f"{original_provision} {mod_phrase} endorsement")

        # Add scope change if provided
        if scope_change:
            parts.append(f"Scope change: {scope_change}")

        # Add limit change if provided
        if limit_change:
            parts.append(f"Limit change: {limit_change}")

        return ". ".join(parts) + "."

    def get_broker_note(self, exclusion_name: str) -> Optional[str]:
        """Get broker guidance note for an exclusion.

        Args:
            exclusion_name: Name of the exclusion.

        Returns:
            Broker guidance note or None if not available.
        """
        template_data = self._find_template_match(
            exclusion_name,
            self.exclusion_templates
        )

        if template_data:
            return template_data.get("broker_note")

        return None

    def get_severity(self, exclusion_name: str) -> str:
        """Get severity rating for an exclusion.

        Args:
            exclusion_name: Name of the exclusion.

        Returns:
            Severity rating (Material, Minor, Administrative).
        """
        template_data = self._find_template_match(
            exclusion_name,
            self.exclusion_templates
        )

        if template_data:
            return template_data.get("severity", "Material")

        return "Material"  # Default to Material for unknown exclusions

    def get_key_features(self, coverage_name: str) -> List[str]:
        """Get key features for a coverage.

        Args:
            coverage_name: Name of the coverage.

        Returns:
            List of key feature strings.
        """
        template_data = self._find_template_match(
            coverage_name,
            self.coverage_templates
        )

        if template_data:
            return template_data.get("key_features", [])

        return []

    async def generate_complex_description(
        self,
        provision_name: str,
        provision_type: str,
        verbatim_text: str,
        context: Optional[DescriptionContext] = None,
    ) -> str:
        """Generate description using LLM for complex provisions.

        This method uses the LLM for provisions that don't match templates
        or have complex verbatim text that needs summarization.

        Args:
            provision_name: Name of the provision.
            provision_type: Type (coverage or exclusion).
            verbatim_text: The verbatim policy text.
            context: Optional context.

        Returns:
            LLM-generated description.
        """
        if not self.llm_client:
            self.logger.warning("No LLM client available for complex description generation")
            return self._generate_fallback_description(provision_name, provision_type)

        prompt = f"""Generate a clear, concise description for this insurance {provision_type}.

Provision Name: {provision_name}
Policy Text: {verbatim_text}

Requirements:
1. Write 1-2 sentences maximum
2. Use plain language suitable for business users
3. Focus on what IS or ISN'T covered
4. Don't include legal jargon unless necessary

Return ONLY the description text, no other commentary."""

        try:
            response = await self.llm_client.generate_content(
                contents=prompt,
                system_instruction="You are an insurance policy analyst who writes clear, concise summaries.",
            )
            return response.strip()
        except Exception as e:
            self.logger.error(f"LLM description generation failed: {e}")
            return self._generate_fallback_description(provision_name, provision_type)

    def _find_template_match(
        self,
        provision_name: str,
        templates: Dict[str, Dict]
    ) -> Optional[Dict]:
        """Find matching template for a provision.

        Uses fuzzy matching to handle variations in naming.

        Args:
            provision_name: Name to match.
            templates: Template dictionary to search.

        Returns:
            Matching template data or None.
        """
        # Exact match
        if provision_name in templates:
            return templates[provision_name]

        # Case-insensitive match
        name_lower = provision_name.lower()
        for template_name, template_data in templates.items():
            if template_name.lower() == name_lower:
                return template_data

        # Partial match (for names like "B.1 Expected Or Intended Injury")
        for template_name, template_data in templates.items():
            if template_name.lower() in name_lower or name_lower in template_name.lower():
                return template_data

        # Key word match
        name_words = set(name_lower.split())
        for template_name, template_data in templates.items():
            template_words = set(template_name.lower().split())
            # If significant overlap in words
            if len(name_words & template_words) >= 2:
                return template_data

        return None

    def _apply_template(
        self,
        template: str,
        template_data: Dict,
        context: Optional[DescriptionContext]
    ) -> str:
        """Apply template with context substitutions.

        Args:
            template: Template string with placeholders.
            template_data: Template data with defaults.
            context: Optional context for overrides.

        Returns:
            Filled template string.
        """
        # Get substitution values
        substitutions = {}

        # Default substitutions from template data
        for key in ["scope", "damages_type", "contract_type", "equipment_type"]:
            default_key = f"default_{key}" if f"default_{key}" in template_data else f"default_scope"
            if default_key in template_data:
                substitutions[key] = template_data[default_key]

        # Override with context if provided
        if context and context.additional_context:
            substitutions.update(context.additional_context)

        # Apply substitutions
        result = template
        for key, value in substitutions.items():
            result = result.replace(f"{{{key}}}", value)

        return result

    def _add_modification_suffix(
        self,
        base_description: str,
        modification_details: str,
        context: Optional[DescriptionContext]
    ) -> str:
        """Add modification suffix to description.

        Args:
            base_description: The base description.
            modification_details: Details of the modification.
            context: Optional context.

        Returns:
            Description with modification suffix.
        """
        # Get endorsement source if available
        endorsement_ref = ""
        if context and context.endorsement_source:
            endorsement_ref = f" by {context.endorsement_source}"

        # Get modification type
        mod_type = "Modified"
        if context and context.modification_type:
            mod_type_map = {
                "expanded": "Expanded",
                "restricted": "Restricted",
                "removed": "Removed",
                "restored": "Restored",
                "narrowed": "Narrowed",
            }
            mod_type = mod_type_map.get(context.modification_type.lower(), "Modified")

        suffix = f" [{mod_type}{endorsement_ref}: {modification_details}]"

        return base_description + suffix

    def _generate_fallback_description(
        self,
        provision_name: str,
        provision_type: str
    ) -> str:
        """Generate fallback description when no template or LLM available.

        Args:
            provision_name: Name of the provision.
            provision_type: Type (coverage or exclusion).

        Returns:
            Generic fallback description.
        """
        if provision_type == "exclusion":
            return f"This insurance does not apply to {provision_name.lower()}-related claims. Review policy language for specific terms and exceptions."
        else:
            return f"Provides coverage for {provision_name.lower()} as defined in the policy. Review policy language for limits, conditions, and exclusions."


def create_description_generator(
    llm_client: Optional[Any] = None
) -> DescriptionGenerator:
    """Factory function to create a DescriptionGenerator.

    Args:
        llm_client: Optional LLM client for complex descriptions.

    Returns:
        Configured DescriptionGenerator instance.
    """
    return DescriptionGenerator(llm_client=llm_client)
