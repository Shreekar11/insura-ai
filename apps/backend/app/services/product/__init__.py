"""Policy Comparison service package.

Primary Services (Entity Comparison - Used by Frontend):
    - PolicyComparisonService: Main service with execute_entity_comparison()
    - EntityComparisonService: Compares coverages and exclusions at entity level
    - EntityMatcherService: Semantic matching using canonical ID + LLM

Deprecated Services (Field-Level Comparison - Legacy Temporal Workflow):
    - SectionAlignmentService: Aligns sections between documents
    - DetailedComparisonService: Field-level comparison within sections
    - PreflightValidator: Validates documents before comparison
    - PolicyComparisonReasoningService: Generates LLM reasoning for field changes

The frontend uses entity comparison which matches a side-by-side comparison
display with match status (MATCH, PARTIAL_MATCH, ADDED, REMOVED).
"""

# Primary services - used by frontend
from .policy_comparison.policy_comparison_service import PolicyComparisonService
from .policy_comparison.entity_comparison_service import EntityComparisonService
from .policy_comparison.entity_matcher_service import EntityMatcherService

# Deprecated services - used by legacy Temporal workflow
from .policy_comparison.preflight_validator import PreflightValidator
from .policy_comparison.section_alignment_service import SectionAlignmentService
from .policy_comparison.detailed_comparison_service import DetailedComparisonService

__all__ = [
    # Primary
    "PolicyComparisonService",
    "EntityComparisonService",
    "EntityMatcherService",
    # Deprecated (legacy)
    "PreflightValidator",
    "SectionAlignmentService",
    "DetailedComparisonService",
]
