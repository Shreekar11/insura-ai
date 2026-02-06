"""Service for entity-level policy comparison."""

from uuid import UUID
from typing import List, Dict, Any, Optional, Literal
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unified_llm import UnifiedLLMClient
from app.core.config import settings
from app.repositories.workflow_output_repository import WorkflowOutputRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.product.policy_comparison import (
    EntityComparison,
    EntityComparisonResult,
    EntityComparisonSummary,
    EntityType,
    MatchType,
)
from app.services.product.policy_comparison.entity_matcher_service import EntityMatcherService
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


class EntityComparisonService:
    """Service for comparing insurance entities at the entity level.

    Compares coverages and exclusions between two documents,
    providing semantic matching and detailed difference analysis.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.matcher_service = EntityMatcherService()
        self.output_repo = WorkflowOutputRepository(session)
        self.document_repo = DocumentRepository(session)
        self.llm_client = UnifiedLLMClient(
            provider=settings.llm_provider,
            api_key=settings.gemini_api_key if settings.llm_provider == "gemini" else settings.openrouter_api_key,
            model=settings.gemini_model if settings.llm_provider == "gemini" else settings.openrouter_model,
            base_url=settings.openrouter_api_url if settings.llm_provider == "openrouter" else None,
        )

    async def compare_entities(
        self,
        workflow_id: UUID,
        doc1_id: UUID,
        doc2_id: UUID,
        doc1_data: Dict[str, Any],
        doc2_data: Dict[str, Any],
    ) -> EntityComparisonResult:
        """Compare entities between two documents.

        Args:
            workflow_id: UUID of the workflow execution
            doc1_id: UUID of document 1 (base/expiring)
            doc2_id: UUID of document 2 (endorsement/renewal)
            doc1_data: Extracted data from document 1
            doc2_data: Extracted data from document 2

        Returns:
            EntityComparisonResult with all entity comparisons
        """
        LOGGER.info(
            f"Starting entity comparison for workflow {workflow_id}",
            extra={
                "workflow_id": str(workflow_id),
                "doc1_id": str(doc1_id),
                "doc2_id": str(doc2_id),
            }
        )

        # Get document names for display
        doc1_name = await self._get_document_name(doc1_id)
        doc2_name = await self._get_document_name(doc2_id)

        # Extract coverages and exclusions from both documents
        doc1_coverages = self._extract_coverages(doc1_data)
        doc2_coverages = self._extract_coverages(doc2_data)
        doc1_exclusions = self._extract_exclusions(doc1_data)
        doc2_exclusions = self._extract_exclusions(doc2_data)

        # Detect if doc2 is an endorsement-only document
        doc2_is_endorsement = self._is_endorsement_only(doc2_data)
        if doc2_is_endorsement:
            LOGGER.info("Detected endorsement-only document in doc2 - enabling endorsement mode")

        LOGGER.info(
            f"Extracted entities - Doc1: {len(doc1_coverages)} coverages, {len(doc1_exclusions)} exclusions; "
            f"Doc2: {len(doc2_coverages)} coverages, {len(doc2_exclusions)} exclusions"
        )

        # Match coverages (with endorsement mode if applicable)
        coverage_matches = await self.matcher_service.match_entities(
            doc1_coverages, doc2_coverages, EntityType.COVERAGE,
            endorsement_mode=doc2_is_endorsement,
        )

        # Match exclusions (with endorsement mode if applicable)
        exclusion_matches = await self.matcher_service.match_entities(
            doc1_exclusions, doc2_exclusions, EntityType.EXCLUSION,
            endorsement_mode=doc2_is_endorsement,
        )

        # Phase: Cross-type reconciliation
        # Find entities representing same concept but classified as different types
        cross_type_matches = await self.matcher_service.find_cross_type_matches(
            doc1_coverages, doc1_exclusions,
            doc2_coverages, doc2_exclusions
        )

        # Build sets of cross-matched entity indices
        cross_matched_coverage_doc1 = set()
        cross_matched_coverage_doc2 = set()
        cross_matched_exclusion_doc1 = set()
        cross_matched_exclusion_doc2 = set()

        for match in cross_type_matches:
            doc1_type = match.get("doc1_type")
            doc2_type = match.get("doc2_type")
            doc1_idx = match.get("doc1_index")
            doc2_idx = match.get("doc2_index")

            if doc1_type == EntityType.COVERAGE:
                cross_matched_coverage_doc1.add(doc1_idx)
            else:
                cross_matched_exclusion_doc1.add(doc1_idx)

            if doc2_type == EntityType.COVERAGE:
                cross_matched_coverage_doc2.add(doc2_idx)
            else:
                cross_matched_exclusion_doc2.add(doc2_idx)

        # Filter type-siloed matches: remove REMOVED/ADDED entries that were cross-matched
        filtered_coverage_matches = [
            m for m in coverage_matches
            if not (
                (m.get("match_type") == MatchType.REMOVED and m.get("doc1_index") in cross_matched_coverage_doc1) or
                (m.get("match_type") == MatchType.ADDED and m.get("doc2_index") in cross_matched_coverage_doc2)
            )
        ]

        filtered_exclusion_matches = [
            m for m in exclusion_matches
            if not (
                (m.get("match_type") == MatchType.REMOVED and m.get("doc1_index") in cross_matched_exclusion_doc1) or
                (m.get("match_type") == MatchType.ADDED and m.get("doc2_index") in cross_matched_exclusion_doc2)
            )
        ]

        LOGGER.info(
            f"Cross-type filtering: "
            f"coverages {len(coverage_matches)} -> {len(filtered_coverage_matches)}, "
            f"exclusions {len(exclusion_matches)} -> {len(filtered_exclusion_matches)}"
        )

        # Convert matches to EntityComparison objects
        comparisons = []

        for match in filtered_coverage_matches:
            comparison = self._create_entity_comparison(match, EntityType.COVERAGE)
            comparisons.append(comparison)

        for match in filtered_exclusion_matches:
            comparison = self._create_entity_comparison(match, EntityType.EXCLUSION)
            comparisons.append(comparison)

        # Add cross-type matches as TYPE_RECLASSIFIED comparisons
        for match in cross_type_matches:
            comparison = self._create_cross_type_comparison(match)
            comparisons.append(comparison)

        # Calculate summary
        summary = self._calculate_summary(
            doc1_coverages, doc2_coverages,
            doc1_exclusions, doc2_exclusions,
            comparisons
        )

        # Calculate overall confidence
        if comparisons:
            overall_confidence = sum(c.confidence for c in comparisons) / len(comparisons)
        else:
            overall_confidence = Decimal("0.0")

        # Generate overall explanation
        overall_explanation = await self._generate_overall_explanation(comparisons)

        result = EntityComparisonResult(
            workflow_id=workflow_id,
            doc1_id=doc1_id,
            doc2_id=doc2_id,
            doc1_name=doc1_name,
            doc2_name=doc2_name,
            summary=summary,
            comparisons=comparisons,
            overall_confidence=overall_confidence,
            overall_explanation=overall_explanation,
            metadata={
                "comparison_version": "1.0",
                "total_comparisons": len(comparisons),
            }
        )

        LOGGER.info(
            f"Entity comparison completed for workflow {workflow_id}",
            extra={
                "total_comparisons": len(comparisons),
                "coverage_matches": summary.coverage_matches,
                "exclusion_matches": summary.exclusion_matches,
            }
        )

        return result

    async def _get_document_name(self, document_id: UUID) -> str:
        """Get the display name for a document."""
        try:
            document = await self.document_repo.get_by_id(document_id)
            if document:
                return document.original_filename or document.title or str(document_id)
        except Exception as e:
            LOGGER.warning(f"Failed to get document name for {document_id}: {e}")
        return str(document_id)

    def _is_endorsement_only(self, data: Dict[str, Any]) -> bool:
        """Detect if data is from an endorsement-only document.

        Endorsement documents only contain modifications to base policy,
        not a complete list of all provisions. This affects how we interpret
        unmatched entities from the base document.

        Args:
            data: Extracted/synthesized data dictionary

        Returns:
            True if this is an endorsement document, False otherwise
        """
        # Check synthesis metadata for endorsement_only method
        synthesis_metadata = data.get("synthesis_metadata", {})
        if not synthesis_metadata and "synthesis_result" in data:
            synthesis_metadata = data["synthesis_result"].get("synthesis_metadata", {})

        synthesis_method = synthesis_metadata.get("synthesis_method", "")
        return synthesis_method == "endorsement_only"

    def _extract_coverages(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract coverages from extracted data."""
        # Try different data structures
        if "effective_coverages" in data:
            return data.get("effective_coverages", [])
        if "synthesis_result" in data and "effective_coverages" in data["synthesis_result"]:
            return data["synthesis_result"].get("effective_coverages", [])
        if "coverages" in data:
            coverages = data.get("coverages", [])
            # Handle nested fields structure
            if isinstance(coverages, dict) and "fields" in coverages:
                return coverages.get("fields", [])
            return coverages if isinstance(coverages, list) else []
        return []

    def _extract_exclusions(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract exclusions from extracted data."""
        # Try different data structures
        if "effective_exclusions" in data:
            return data.get("effective_exclusions", [])
        if "synthesis_result" in data and "effective_exclusions" in data["synthesis_result"]:
            return data["synthesis_result"].get("effective_exclusions", [])
        if "exclusions" in data:
            exclusions = data.get("exclusions", [])
            # Handle nested fields structure
            if isinstance(exclusions, dict) and "fields" in exclusions:
                return exclusions.get("fields", [])
            return exclusions if isinstance(exclusions, list) else []
        return []

    def _create_entity_comparison(
        self,
        match: Dict[str, Any],
        entity_type: EntityType
    ) -> EntityComparison:
        """Create an EntityComparison from a match result."""
        doc1_entity = match.get("doc1_entity")
        doc2_entity = match.get("doc2_entity")

        # Extract names
        doc1_name = None
        doc2_name = None
        doc1_canonical_id = None
        doc2_canonical_id = None

        if doc1_entity:
            if entity_type == EntityType.COVERAGE:
                doc1_name = doc1_entity.get("coverage_name") or doc1_entity.get("name")
            else:
                doc1_name = doc1_entity.get("exclusion_name") or doc1_entity.get("title")
            doc1_canonical_id = doc1_entity.get("canonical_id")

        if doc2_entity:
            if entity_type == EntityType.COVERAGE:
                doc2_name = doc2_entity.get("coverage_name") or doc2_entity.get("name")
            else:
                doc2_name = doc2_entity.get("exclusion_name") or doc2_entity.get("title")
            doc2_canonical_id = doc2_entity.get("canonical_id")

        # Determine severity based on match type
        match_type = match.get("match_type")
        if match_type == MatchType.MATCH:
            severity = "low"
        elif match_type == MatchType.UNCHANGED:
            severity = "low"  # Unchanged entities are not concerning
        elif match_type == MatchType.PARTIAL_MATCH:
            severity = "medium"
        elif match_type == MatchType.TYPE_RECLASSIFIED:
            severity = "high"  # Misclassification indicates data quality issue
        else:  # ADDED, REMOVED
            severity = "high"

        return EntityComparison(
            entity_type=entity_type,
            match_type=match_type,
            doc1_entity=doc1_entity,
            doc1_name=doc1_name,
            doc1_canonical_id=doc1_canonical_id,
            doc2_entity=doc2_entity,
            doc2_name=doc2_name,
            doc2_canonical_id=doc2_canonical_id,
            confidence=match.get("confidence", Decimal("0.0")),
            match_method=match.get("match_method", "unknown"),
            field_differences=match.get("field_differences"),
            reasoning=match.get("reasoning"),
            severity=severity,
        )

    def _create_cross_type_comparison(
        self,
        match: Dict[str, Any],
    ) -> EntityComparison:
        """Create an EntityComparison from a cross-type match result.

        Cross-type matches indicate the same insurance concept is classified as
        different entity types (Coverage vs Exclusion) in the two documents.

        Args:
            match: Cross-type match result with doc1_type, doc2_type fields

        Returns:
            EntityComparison with TYPE_RECLASSIFIED match type
        """
        doc1_entity = match.get("doc1_entity")
        doc2_entity = match.get("doc2_entity")
        doc1_type = match.get("doc1_type")
        doc2_type = match.get("doc2_type")

        # Extract names based on actual entity types
        doc1_name = None
        doc2_name = None
        doc1_canonical_id = None
        doc2_canonical_id = None

        if doc1_entity:
            if doc1_type == EntityType.COVERAGE:
                doc1_name = doc1_entity.get("coverage_name") or doc1_entity.get("name")
            else:
                doc1_name = doc1_entity.get("exclusion_name") or doc1_entity.get("title")
            doc1_canonical_id = doc1_entity.get("canonical_id")

        if doc2_entity:
            if doc2_type == EntityType.COVERAGE:
                doc2_name = doc2_entity.get("coverage_name") or doc2_entity.get("name")
            else:
                doc2_name = doc2_entity.get("exclusion_name") or doc2_entity.get("title")
            doc2_canonical_id = doc2_entity.get("canonical_id")

        # Use doc1's entity type as the primary type for this comparison
        # (could also be doc2_type - choice is arbitrary since they differ)
        entity_type = doc1_type

        # Enhance reasoning to indicate type mismatch
        base_reasoning = match.get("reasoning", "Same concept classified as different entity type")
        enhanced_reasoning = (
            f"{base_reasoning} "
            f"(Doc1: {doc1_type.value}, Doc2: {doc2_type.value})"
        )

        return EntityComparison(
            entity_type=entity_type,
            match_type=MatchType.TYPE_RECLASSIFIED,
            doc1_entity=doc1_entity,
            doc1_name=doc1_name,
            doc1_canonical_id=doc1_canonical_id,
            doc2_entity=doc2_entity,
            doc2_name=doc2_name,
            doc2_canonical_id=doc2_canonical_id,
            confidence=match.get("confidence", Decimal("0.0")),
            match_method=match.get("match_method", "cross_type_llm"),
            field_differences=None,  # Type mismatch is conceptual, not field-level
            reasoning=enhanced_reasoning,
            severity="high",  # Misclassification is a data quality issue
        )

    def _calculate_summary(
        self,
        doc1_coverages: List[Dict],
        doc2_coverages: List[Dict],
        doc1_exclusions: List[Dict],
        doc2_exclusions: List[Dict],
        comparisons: List[EntityComparison],
    ) -> EntityComparisonSummary:
        """Calculate summary statistics from comparisons."""
        coverage_matches = 0
        coverage_partial_matches = 0
        coverages_added = 0
        coverages_removed = 0
        coverages_unchanged = 0

        exclusion_matches = 0
        exclusion_partial_matches = 0
        exclusions_added = 0
        exclusions_removed = 0
        exclusions_unchanged = 0

        entities_reclassified = 0

        for c in comparisons:
            if c.match_type == MatchType.TYPE_RECLASSIFIED:
                entities_reclassified += 1
            elif c.entity_type == EntityType.COVERAGE:
                if c.match_type == MatchType.MATCH:
                    coverage_matches += 1
                elif c.match_type == MatchType.PARTIAL_MATCH:
                    coverage_partial_matches += 1
                elif c.match_type == MatchType.ADDED:
                    coverages_added += 1
                elif c.match_type == MatchType.REMOVED:
                    coverages_removed += 1
                elif c.match_type == MatchType.UNCHANGED:
                    coverages_unchanged += 1
            else:  # EXCLUSION
                if c.match_type == MatchType.MATCH:
                    exclusion_matches += 1
                elif c.match_type == MatchType.PARTIAL_MATCH:
                    exclusion_partial_matches += 1
                elif c.match_type == MatchType.ADDED:
                    exclusions_added += 1
                elif c.match_type == MatchType.REMOVED:
                    exclusions_removed += 1
                elif c.match_type == MatchType.UNCHANGED:
                    exclusions_unchanged += 1

        return EntityComparisonSummary(
            total_coverages_doc1=len(doc1_coverages),
            total_coverages_doc2=len(doc2_coverages),
            total_exclusions_doc1=len(doc1_exclusions),
            total_exclusions_doc2=len(doc2_exclusions),
            coverage_matches=coverage_matches,
            coverage_partial_matches=coverage_partial_matches,
            coverages_added=coverages_added,
            coverages_removed=coverages_removed,
            coverages_unchanged=coverages_unchanged,
            exclusion_matches=exclusion_matches,
            exclusion_partial_matches=exclusion_partial_matches,
            exclusions_added=exclusions_added,
            exclusions_removed=exclusions_removed,
            exclusions_unchanged=exclusions_unchanged,
            entities_reclassified=entities_reclassified,
        )

    async def _generate_overall_explanation(
        self,
        comparisons: List[EntityComparison],
    ) -> Optional[str]:
        """Generate an LLM-powered overall explanation of the comparison."""
        if not comparisons:
            return "No entities to compare."

        # Filter material changes (exclude UNCHANGED and exact MATCH)
        material_changes = [
            c for c in comparisons
            if c.match_type in [MatchType.PARTIAL_MATCH, MatchType.ADDED, MatchType.REMOVED, MatchType.TYPE_RECLASSIFIED]
        ]

        if not material_changes:
            return "All coverages and exclusions match between the two documents."

        # Prepare summary for LLM
        summary_lines = []
        for c in material_changes[:20]:  # Limit to 20 changes
            entity_name = c.doc1_name or c.doc2_name or "Unknown"
            if c.match_type == MatchType.ADDED:
                summary_lines.append(f"- ADDED {c.entity_type.value}: {entity_name}")
            elif c.match_type == MatchType.REMOVED:
                summary_lines.append(f"- REMOVED {c.entity_type.value}: {entity_name}")
            elif c.match_type == MatchType.PARTIAL_MATCH:
                summary_lines.append(f"- MODIFIED {c.entity_type.value}: {entity_name}")
            elif c.match_type == MatchType.TYPE_RECLASSIFIED:
                summary_lines.append(f"- RECLASSIFIED: {entity_name} (appears as different entity type in documents)")

        prompt = f"""You are an insurance policy expert. Summarize the following differences between two insurance policies.
Focus on the most important changes that affect coverage for the policyholder.

Changes detected:
{chr(10).join(summary_lines)}

Provide a concise summary (2-3 sentences) highlighting the key differences a broker or policyholder should be aware of.
"""

        try:
            response = await self.llm_client.generate_content(contents=prompt)
            return response.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate overall explanation: {e}", exc_info=True)
            return f"Found {len(material_changes)} material differences between the policies."
