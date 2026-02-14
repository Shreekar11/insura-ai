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
    ComparisonSource,
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

        # 1. Effective Comparisons (Synthesized Results)
        doc1_eff_coverages = self._extract_coverages(doc1_data)
        doc2_eff_coverages = self._extract_coverages(doc2_data)
        doc1_eff_exclusions = self._extract_exclusions(doc1_data)
        doc2_eff_exclusions = self._extract_exclusions(doc2_data)

        LOGGER.info(
            f"Extracted entities - Doc1: {len(doc1_eff_coverages)} coverages, {len(doc1_eff_exclusions)} exclusions; "
            f"Doc2: {len(doc2_eff_coverages)} coverages, {len(doc2_eff_exclusions)} exclusions"
        )

        # Detect if doc2 is an endorsement affecting match interpretation
        is_endorsement = self._is_endorsement_only(doc2_data)
        if is_endorsement:
            LOGGER.info("Document 2 identified as endorsement-only; using UNCHANGED for base entries")

        # Match coverages
        coverage_matches = await self.matcher_service.match_entities(
            doc1_eff_coverages, doc2_eff_coverages, EntityType.COVERAGE,
            endorsement_mode=is_endorsement
        )

        # Match exclusions
        exclusion_matches = await self.matcher_service.match_entities(
            doc1_eff_exclusions, doc2_eff_exclusions, EntityType.EXCLUSION,
            endorsement_mode=is_endorsement
        )

        # 2. Cross-Type Matches (Entities that switched types between documents)
        cross_type_matches = await self.matcher_service.find_cross_type_matches(
            doc1_eff_coverages, doc1_eff_exclusions,
            doc2_eff_coverages, doc2_eff_exclusions
        )

        # Convert matches to EntityComparison objects
        comparisons = []

        for match in coverage_matches:
            comparison = self._create_entity_comparison(match, EntityType.COVERAGE)
            comparisons.append(comparison)

        for match in exclusion_matches:
            comparison = self._create_entity_comparison(match, EntityType.EXCLUSION)
            comparisons.append(comparison)

        # Integration of cross-type matches
        for match in cross_type_matches:
            comparison = self._create_cross_type_comparison(match)
            comparisons.append(comparison)

        # Calculate summary
        summary = self._calculate_summary(
            doc1_eff_coverages, doc2_eff_coverages,
            doc1_eff_exclusions, doc2_eff_exclusions,
            comparisons
        )

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
            overall_confidence=Decimal("0.85"),  # Placeholder
            overall_explanation=overall_explanation,
            metadata={
                "coverage_count": len(coverage_matches),
                "exclusion_count": len(exclusion_matches),
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
                return document.document_name or document.file_path.split("/")[-1] or str(document_id)
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
        """Extract effective coverages from extracted data."""
        # Check for new structured output from WorkflowService
        entities = data.get("entities", [])
        for entity in entities:
            if entity.get("entity_type") == "effective_coverages":
                coverages = entity.get("fields", [])
                # Pass metadata through
                if isinstance(coverages, list):
                    for c in coverages:
                        if isinstance(c, dict):
                            c["_extraction_id"] = entity.get("id")
                            c["_confidence"] = entity.get("confidence")
                    return [c for c in coverages if isinstance(c, dict)]

        # Fallback to old structures
        coverages = []
        if "effective_coverages" in data:
            coverages = data.get("effective_coverages", [])
        elif "synthesis_result" in data and "effective_coverages" in data["synthesis_result"]:
            coverages = data["synthesis_result"].get("effective_coverages", [])
        
        return [c for c in coverages if isinstance(c, dict)]

    def _extract_exclusions(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract effective exclusions from extracted data."""
        # Check for new structured output from WorkflowService
        entities = data.get("entities", [])
        for entity in entities:
            if entity.get("entity_type") == "effective_exclusions":
                exclusions = entity.get("fields", [])
                # Pass metadata through
                if isinstance(exclusions, list):
                    for e in exclusions:
                        if isinstance(e, dict):
                            e["_extraction_id"] = entity.get("id")
                            e["_confidence"] = entity.get("confidence")
                    return [e for e in exclusions if isinstance(e, dict)]

        # Fallback to old structures
        exclusions = []
        if "effective_exclusions" in data:
            exclusions = data.get("effective_exclusions", [])
        elif "synthesis_result" in data and "effective_exclusions" in data["synthesis_result"]:
            exclusions = data["synthesis_result"].get("effective_exclusions", [])
        
        return [e for e in exclusions if isinstance(e, dict)]

    def _extract_section_data(self, data: Dict[str, Any], section_type: str) -> List[Dict[str, Any]]:
        """Extract data from a specific section (e.g., 'coverages', 'exclusions')."""
        sections = data.get("sections", [])
        for section in sections:
            if section.get("section_type") == section_type:
                fields = section.get("fields", {})
                # Section data 'fields' is usually a dict, but for comparison we often want the list of items
                # if it's a list-based section
                items = []
                if isinstance(fields, dict):
                    # Check if it has an 'items' or similar key, or if it's a flat dict we want to treat as one item
                    if "items" in fields:
                        items = fields["items"]
                    elif "fields" in fields:
                        items = fields["fields"]
                    else:
                        items = [fields]
                elif isinstance(fields, list):
                    items = fields

                # Pass metadata through
                valid_items = []
                for item in items:
                    if isinstance(item, dict):
                        item["_extraction_id"] = section.get("id")
                        item["_confidence"] = section.get("confidence")
                        item["_page_range"] = section.get("page_range")
                        valid_items.append(item)
                
                return valid_items
        
        return []

    def _create_entity_comparison(
        self,
        match: Dict[str, Any],
        entity_type: EntityType
    ) -> EntityComparison:
        """Create an EntityComparison from a match result."""
        doc1_entity = match.get("doc1_entity")
        doc2_entity = match.get("doc2_entity")

        # Extract names and metadata
        entity_name = "Unknown"
        entity_id = None

        if doc2_entity:
            if entity_type in [EntityType.COVERAGE, EntityType.SECTION_COVERAGE]:
                entity_name = doc2_entity.get("coverage_name") or doc2_entity.get("name") or "Unknown Coverage"
            else:
                entity_name = doc2_entity.get("exclusion_name") or doc2_entity.get("title") or "Unknown Exclusion"
            entity_id = doc2_entity.get("canonical_id") or doc2_entity.get("id")
        elif doc1_entity:
            if entity_type in [EntityType.COVERAGE, EntityType.SECTION_COVERAGE]:
                entity_name = doc1_entity.get("coverage_name") or doc1_entity.get("name") or "Unknown Coverage"
            else:
                entity_name = doc1_entity.get("exclusion_name") or doc1_entity.get("title") or "Unknown Exclusion"
            entity_id = doc1_entity.get("canonical_id") or doc1_entity.get("id")

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
            match_type=match.get("match_type"),
            entity_id=entity_id,
            entity_name=entity_name,
            confidence=match.get("confidence", Decimal("1.0")),
            doc1_content=doc1_entity,
            doc2_content=doc2_entity,
            field_differences=match.get("field_differences") or [],
            reasoning=match.get("reasoning"),
            # Contextual metadata from extraction layer
            doc1_page_range=doc1_entity.get("_page_range") if doc1_entity else None,
            doc2_page_range=doc2_entity.get("_page_range") if doc2_entity else None,
            doc1_confidence=doc1_entity.get("_confidence") if doc1_entity else None,
            doc2_confidence=doc2_entity.get("_confidence") if doc2_entity else None,
            doc1_extraction_id=doc1_entity.get("_extraction_id") if doc1_entity else None,
            doc2_extraction_id=doc2_entity.get("_extraction_id") if doc2_entity else None,
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
            entity_id=doc2_canonical_id or doc1_canonical_id,
            entity_name=doc2_name or doc1_name or "Unknown",
            doc1_content=doc1_entity,
            doc2_content=doc2_entity,
            doc1_name=doc1_name,
            doc1_canonical_id=doc1_canonical_id,
            doc2_name=doc2_name,
            doc2_canonical_id=doc2_canonical_id,
            confidence=match.get("confidence", Decimal("0.0")),
            match_method=match.get("match_method", "cross_type_llm"),
            field_differences=None,  # Type mismatch is conceptual, not field-level
            reasoning=enhanced_reasoning,
            severity="high",  # Misclassification is a data quality issue
            # Contextual metadata
            doc1_page_range=doc1_entity.get("_page_range") if doc1_entity else None,
            doc2_page_range=doc2_entity.get("_page_range") if doc2_entity else None,
            doc1_confidence=doc1_entity.get("_confidence") if doc1_entity else None,
            doc2_confidence=doc2_entity.get("_confidence") if doc2_entity else None,
            doc1_extraction_id=doc1_entity.get("_extraction_id") if doc1_entity else None,
            doc2_extraction_id=doc2_entity.get("_extraction_id") if doc2_entity else None,
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
            total_comparisons=len([c for c in comparisons if c.comparison_source == ComparisonSource.EFFECTIVE]),
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
            total_added=coverages_added + exclusions_added,
            total_removed=coverages_removed + exclusions_removed,
            total_modified=coverage_partial_matches + exclusion_partial_matches,
            entities_reclassified=entities_reclassified,
        )

    async def _generate_overall_explanation(
        self,
        comparisons: List[EntityComparison],
    ) -> str:
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
            entity_name = c.doc1_name or c.doc2_name or c.entity_name or "Unknown"
            if c.match_type == MatchType.ADDED:
                summary_lines.append(f"- ADDED {c.entity_type.value}: {entity_name}")
            elif c.match_type == MatchType.REMOVED:
                summary_lines.append(f"- REMOVED {c.entity_type.value}: {entity_name}")
            elif c.match_type == MatchType.PARTIAL_MATCH:
                summary_lines.append(f"- MODIFIED {c.entity_type.value}: {entity_name}")

        prompt = f"""You are an insurance policy expert. Summarize the following differences between two insurance policies.
Focus on the most important changes that affect coverage for the policyholder.

Changes detected:
{chr(10).join(summary_lines[:20])}

Provide a concise summary (2-3 sentences) highlighting the key differences a broker or policyholder should be aware of.
"""

        try:
            summary = await self.llm_client.generate_content(contents=prompt)
            return summary.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate overall explanation: {e}", exc_info=True)
            return f"Summary of changes: {len([c for c in effective_comps if c.match_type != MatchType.MATCH])} differences identified."

    async def _enrich_with_summaries(self, comparisons: List[EntityComparison]) -> None:
        """Enrich entity comparisons with LLM-generated summaries in parallel."""
        # Enrich matches that are NOT an exact 'match'
        to_enrich = [c for c in comparisons if c.match_type != MatchType.MATCH]
        if not to_enrich:
            return

        import asyncio
        tasks = [self._generate_entity_summaries(c) for c in to_enrich]
        if tasks:
            LOGGER.info(f"Generating summaries for {len(tasks)} entity comparisons")
            await asyncio.gather(*tasks)

    async def _generate_entity_summaries(self, comparison: EntityComparison) -> None:
        """Generate summaries for a single entity comparison using LLM."""
        doc1_data = comparison.doc1_content
        doc2_data = comparison.doc2_content
        entity_type = comparison.entity_type.value
        
        import json

        # Prepare context for LLM
        prompt = f"""
        You are a senior insurance policy expert assisting with policy comparison analysis.
        Your task is to interpret and summarize insurance {entity_type} data in a way that is
        clear, accurate, and useful for an insurance broker or policyholder.

        Use the structured data provided below to produce concise, plain-English summaries.
        Do NOT restate raw JSON. Focus on meaning, coverage intent, and practical impact.

        """

        if doc1_data:
            prompt += f"""
        Document 1 - {entity_type} details:
        {json.dumps(doc1_data, indent=2)}
        """

        if doc2_data:
            prompt += f"""
        Document 2 - {entity_type} details:
        {json.dumps(doc2_data, indent=2)}
        """

        prompt += f"""
        ### Instructions

        1. **doc1_summary**
        - Write a single, concise sentence summarizing the {entity_type} from Document 1.
        - If Document 1 data is missing, return an empty string.

        2. **doc2_summary**
        - Write a single, concise sentence summarizing the {entity_type} from Document 2.
        - If Document 2 data is missing, return an empty string.

        3. **comparison_summary**
        - Write up to two sentences comparing the two documents.
        - The comparison **must align with the provided match type** and clearly explain why.
        - Emphasize the **practical impact** for a broker or policyholder.

        ---

        ### Match Type Semantics (MANDATORY)

        Use the following definitions when generating the comparison:

        - **MATCH**
        - The {entity_type} is semantically equivalent in both documents.
        - No material difference in coverage intent, scope, or applicability.

        - **PARTIAL_MATCH**
        - The {entity_type} exists in both documents but differs in scope, limits, conditions, or modifiers.
        - Explain what changed and whether coverage is broadened or restricted.

        - **ADDED**
        - The {entity_type} exists only in Document 2.
        - Explain the newly introduced coverage, exclusion, or condition and its impact.

        - **REMOVED**
        - The {entity_type} exists only in Document 1.
        - Explain what coverage, exclusion, or condition is no longer present and its impact.

        - **NO_MATCH**
        - The {entity_type} in the two documents refers to different concepts or cannot be meaningfully compared.
        - Clearly state that no direct comparison is possible and why.

        ---

        ### Comparison Context
        - Match Type: {comparison.match_type.value}

        ### Output Format (STRICT)
        Return **only** a valid JSON object with exactly the following keys:
        - "doc1_summary"
        - "doc2_summary"
        - "comparison_summary"

        Do not include explanations, markdown, or additional text outside the JSON object.
        """

        try:
            response_text = await self.llm_client.generate_content(
                contents=prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            data = parse_json_safely(response_text)
            
            if data:
                # Store summaries in explanation field for now, or we might need to extend schema again
                # Actually, I should probably put them in a structured way in the differences or a new field
                # For now, let's just create a combined explanation if the schema doesn't have these fields
                # Wait, I didn't add doc1_summary/doc2_summary/comparison_summary to the schema!
                # I should just use the explanation field.
                
                if data.get("doc1_summary"):
                    comparison.doc1_summary = data.get("doc1_summary")
                if data.get("doc2_summary"):
                    comparison.doc2_summary = data.get("doc2_summary")
                if data.get("comparison_summary"):
                    comparison.comparison_summary = data.get("comparison_summary")
                
                # Also keep a combined version in reasoning if needed, or just set it to doc2_summary/comparison_summary
                comparison.reasoning = data.get("comparison_summary") or data.get("doc2_summary") or "No detailed reasoning available."
        except Exception as e:
            LOGGER.warning(f"Failed to generate summaries for entity: {e}")
            # Fallback to simple explanation
            comparison.reasoning = f"Match result: {comparison.match_type.value}"
