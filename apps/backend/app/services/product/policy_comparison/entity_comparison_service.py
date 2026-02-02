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

        LOGGER.info(
            f"Extracted entities - Doc1: {len(doc1_coverages)} coverages, {len(doc1_exclusions)} exclusions; "
            f"Doc2: {len(doc2_coverages)} coverages, {len(doc2_exclusions)} exclusions"
        )

        # Match coverages
        coverage_matches = await self.matcher_service.match_entities(
            doc1_coverages, doc2_coverages, EntityType.COVERAGE
        )

        # Match exclusions
        exclusion_matches = await self.matcher_service.match_entities(
            doc1_exclusions, doc2_exclusions, EntityType.EXCLUSION
        )

        # Convert matches to EntityComparison objects
        comparisons = []

        for match in coverage_matches:
            comparison = self._create_entity_comparison(match, EntityType.COVERAGE)
            comparisons.append(comparison)

        for match in exclusion_matches:
            comparison = self._create_entity_comparison(match, EntityType.EXCLUSION)
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
        elif match_type == MatchType.PARTIAL_MATCH:
            severity = "medium"
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

        exclusion_matches = 0
        exclusion_partial_matches = 0
        exclusions_added = 0
        exclusions_removed = 0

        for c in comparisons:
            if c.entity_type == EntityType.COVERAGE:
                if c.match_type == MatchType.MATCH:
                    coverage_matches += 1
                elif c.match_type == MatchType.PARTIAL_MATCH:
                    coverage_partial_matches += 1
                elif c.match_type == MatchType.ADDED:
                    coverages_added += 1
                elif c.match_type == MatchType.REMOVED:
                    coverages_removed += 1
            else:  # EXCLUSION
                if c.match_type == MatchType.MATCH:
                    exclusion_matches += 1
                elif c.match_type == MatchType.PARTIAL_MATCH:
                    exclusion_partial_matches += 1
                elif c.match_type == MatchType.ADDED:
                    exclusions_added += 1
                elif c.match_type == MatchType.REMOVED:
                    exclusions_removed += 1

        return EntityComparisonSummary(
            total_coverages_doc1=len(doc1_coverages),
            total_coverages_doc2=len(doc2_coverages),
            total_exclusions_doc1=len(doc1_exclusions),
            total_exclusions_doc2=len(doc2_exclusions),
            coverage_matches=coverage_matches,
            coverage_partial_matches=coverage_partial_matches,
            coverages_added=coverages_added,
            coverages_removed=coverages_removed,
            exclusion_matches=exclusion_matches,
            exclusion_partial_matches=exclusion_partial_matches,
            exclusions_added=exclusions_added,
            exclusions_removed=exclusions_removed,
        )

    async def _generate_overall_explanation(
        self,
        comparisons: List[EntityComparison],
    ) -> Optional[str]:
        """Generate an LLM-powered overall explanation of the comparison."""
        if not comparisons:
            return "No entities to compare."

        # Filter material changes
        material_changes = [
            c for c in comparisons
            if c.match_type in [MatchType.PARTIAL_MATCH, MatchType.ADDED, MatchType.REMOVED]
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
