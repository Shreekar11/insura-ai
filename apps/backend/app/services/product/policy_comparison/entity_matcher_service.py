"""Service for semantic matching of insurance entities across documents."""

import json
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from app.core.unified_llm import UnifiedLLMClient
from app.core.config import settings
from app.schemas.product.policy_comparison import MatchType, EntityType
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


class EntityMatcherService:
    """Service for matching insurance entities (coverages, exclusions) across documents.

    Uses a hybrid approach:
    1. First attempts canonical_id matching (fast, deterministic)
    2. Falls back to LLM semantic matching for entities without canonical_id or no direct match
    """

    def __init__(self):
        self.client = UnifiedLLMClient(
            provider=settings.llm_provider,
            api_key=settings.gemini_api_key if settings.llm_provider == "gemini" else settings.openrouter_api_key,
            model=settings.gemini_model if settings.llm_provider == "gemini" else settings.openrouter_model,
            base_url=settings.openrouter_api_url if settings.llm_provider == "openrouter" else None,
        )

    async def match_entities(
        self,
        doc1_entities: List[Dict[str, Any]],
        doc2_entities: List[Dict[str, Any]],
        entity_type: EntityType,
    ) -> List[Dict[str, Any]]:
        """Match entities between two documents.

        Args:
            doc1_entities: List of entities from document 1 (base/expiring)
            doc2_entities: List of entities from document 2 (endorsement/renewal)
            entity_type: Type of entities being matched

        Returns:
            List of match results, each containing doc1_entity, doc2_entity, 
            match_type, and list of differences.
        """
        if not doc1_entities and not doc2_entities:
            return []

        LOGGER.info(
            f"Matching {len(doc1_entities)} items from Doc1 and {len(doc2_entities)} items from Doc2 "
            f"for type {entity_type.value}"
        )

        # 1. Match by canonical_id (and 'id' for section data)
        matches, unmatched_doc1, unmatched_doc2 = await self._match_by_canonical_id(
            doc1_entities, doc2_entities, entity_type
        )

        # 2. Match remaining using LLM
        if unmatched_doc1 and unmatched_doc2:
            llm_matches = await self._match_by_llm(
                unmatched_doc1, unmatched_doc2, entity_type
            )
            matches.extend(llm_matches)

        # 3. Handle unmatched as ADDED or REMOVED
        matched_doc1_indices = {m["doc1_index"] for m in matches if m.get("doc1_index") is not None}
        matched_doc2_indices = {m["doc2_index"] for m in matches if m.get("doc2_index") is not None}

        for i, entity in enumerate(doc1_entities):
            if i not in matched_doc1_indices:
                matches.append({
                    "match_type": MatchType.REMOVED,
                    "doc1_entity": entity,
                    "doc2_entity": None,
                    "field_differences": [],
                    "doc1_index": i,
                    "doc2_index": None,
                })

        for i, entity in enumerate(doc2_entities):
            if i not in matched_doc2_indices:
                matches.append({
                    "match_type": MatchType.ADDED,
                    "doc1_entity": None,
                    "doc2_entity": entity,
                    "field_differences": [],
                    "doc1_index": None,
                    "doc2_index": i,
                })

        return matches

    async def _match_by_canonical_id(
        self,
        doc1_entities: List[Dict[str, Any]],
        doc2_entities: List[Dict[str, Any]],
        entity_type: EntityType,
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[int, Dict[str, Any]]], List[Tuple[int, Dict[str, Any]]]]:
        """Match entities using canonical_id field or section-level stable IDs."""
        matches = []
        doc1_map = {}
        
        # Determine ID fields based on type
        id_fields = ["canonical_id"]
        if entity_type in [EntityType.SECTION_COVERAGE, EntityType.SECTION_EXCLUSION]:
            id_fields.append("id")  # Fallback to internal ID for section data

        for i, entity in enumerate(doc1_entities):
            for id_field in id_fields:
                val = entity.get(id_field)
                if val:
                    doc1_map[val] = (i, entity)
                    break

        matched_doc2_indices = set()
        for j, doc2_entity in enumerate(doc2_entities):
            match_val = None
            for id_field in id_fields:
                val = doc2_entity.get(id_field)
                if val and val in doc1_map:
                    match_val = val
                    break
            
            if match_val:
                i, doc1_entity = doc1_map[match_val]
                match_type, differences = self._compare_entity_fields(
                    doc1_entity, doc2_entity, entity_type
                )
                matches.append({
                    "doc1_index": i,
                    "doc2_index": j,
                    "match_type": match_type,
                    "doc1_entity": doc1_entity,
                    "doc2_entity": doc2_entity,
                    "field_differences": differences,
                    "confidence": Decimal("1.0"),
                    "match_method": "canonical_id",
                })
                matched_doc2_indices.add(j)
                # Remove from map to prevent double matching
                doc1_map.pop(match_val)

        unmatched_doc1 = [val for val in doc1_map.values()]
        unmatched_doc2 = [
            (j, entity) for j, entity in enumerate(doc2_entities) 
            if j not in matched_doc2_indices
        ]

        return matches, unmatched_doc1, unmatched_doc2

    async def _match_by_llm(
        self,
        unmatched_doc1: List[Tuple[int, Dict[str, Any]]],
        unmatched_doc2: List[Tuple[int, Dict[str, Any]]],
        entity_type: EntityType,
    ) -> List[Dict[str, Any]]:
        """Match entities using LLM semantic analysis."""
        if not unmatched_doc1 and not unmatched_doc2:
            return []

        # Prepare simplified entities for LLM
        doc1_simplified = [
            {
                "index": i,
                "name": self._get_entity_name(e, entity_type),
                "description": e.get("description") or e.get("scope") or "",
            }
            for i, e in unmatched_doc1
        ]

        doc2_simplified = [
            {
                "index": i,
                "name": self._get_entity_name(e, entity_type),
                "description": e.get("description") or e.get("scope") or "",
            }
            for i, e in unmatched_doc2
        ]

        prompt = self._get_matching_prompt(
            doc1_simplified, doc2_simplified, entity_type
        )

        try:
            response = await self.client.generate_content(
                contents=prompt,
                generation_config={"response_mime_type": "application/json"}
            )

            llm_matches = parse_json_safely(response)

            if not isinstance(llm_matches, list):
                LOGGER.warning("LLM matching returned invalid format")
                return []

            # Convert LLM results to match format
            matches = []
            for llm_match in llm_matches:
                doc1_idx = llm_match.get("doc1_index")
                doc2_idx = llm_match.get("doc2_index")
                match_type_str = llm_match.get("match_type", "no_match")
                confidence = Decimal(str(llm_match.get("confidence", 0.8)))

                # Map string to enum
                if match_type_str == "match":
                    match_type = MatchType.MATCH
                elif match_type_str == "partial_match":
                    match_type = MatchType.PARTIAL_MATCH
                else:
                    continue  # Skip no_match results from LLM

                # Find original entities
                doc1_entity = None
                doc2_entity = None
                for i, e in unmatched_doc1:
                    if i == doc1_idx:
                        doc1_entity = e
                        break
                for i, e in unmatched_doc2:
                    if i == doc2_idx:
                        doc2_entity = e
                        break

                if doc1_entity and doc2_entity:
                    _, differences = self._compare_entity_fields(
                        doc1_entity, doc2_entity, entity_type
                    )

                    matches.append({
                        "match_type": match_type,
                        "doc1_index": doc1_idx,
                        "doc1_entity": doc1_entity,
                        "doc2_index": doc2_idx,
                        "doc2_entity": doc2_entity,
                        "confidence": confidence,
                        "match_method": "llm_semantic",
                        "field_differences": differences if differences else None,
                        "reasoning": llm_match.get("reasoning", "Semantic match by LLM"),
                    })

            LOGGER.debug(f"LLM matching found {len(matches)} matches")
            return matches

        except Exception as e:
            LOGGER.error(f"LLM matching failed: {e}", exc_info=True)
            return []

    def _get_entity_name(self, entity: Dict[str, Any], entity_type: EntityType) -> str:
        """Extract the primary name from an entity."""
        if entity_type == EntityType.COVERAGE:
            return entity.get("coverage_name") or entity.get("name") or "Unknown Coverage"
        else:
            return entity.get("exclusion_name") or entity.get("title") or "Unknown Exclusion"

    def _compare_entity_fields(
        self,
        doc1_entity: Dict[str, Any],
        doc2_entity: Dict[str, Any],
        entity_type: EntityType,
    ) -> Tuple[MatchType, List[Dict[str, Any]]]:
        """Compare fields between two entities to determine match type.

        Returns:
            Tuple of (match_type, list of field differences)
        """
        # Define key fields to compare based on entity type
        if entity_type == EntityType.COVERAGE:
            key_fields = [
                "coverage_name", "coverage_type", "limit_amount", "deductible_amount",
                "premium_amount", "effective_terms", "limits", "deductibles"
            ]
        elif entity_type == EntityType.EXCLUSION:
            key_fields = [
                "exclusion_name", "effective_state", "scope", "carve_backs",
                "conditions", "impacted_coverages"
            ]
        elif entity_type == EntityType.SECTION_COVERAGE:
            key_fields = [
                "name", "coverage_basis", "coverage_category", "limit_aggregate",
                "limit_per_occurrence", "deductible_per_occurrence", "description"
            ]
        elif entity_type == EntityType.SECTION_EXCLUSION:
            key_fields = [
                "title", "description", "exception_carveback", "applicability",
                "impacted_sections"
            ]
        else:
            key_fields = []

        differences = []
        for field in key_fields:
            val1 = doc1_entity.get(field)
            val2 = doc2_entity.get(field)

            # Skip comparison if both are None
            if val1 is None and val2 is None:
                continue

            # Handle different types of inequality (using string representation for complex types)
            if str(val1) != str(val2):
                differences.append({
                    "field": field,
                    "doc1_value": val1,
                    "doc2_value": val2,
                })

        if not differences:
            return MatchType.MATCH, []
        else:
            return MatchType.PARTIAL_MATCH, differences

    def _get_matching_prompt(
        self,
        doc1_entities: List[Dict[str, Any]],
        doc2_entities: List[Dict[str, Any]],
        entity_type: EntityType,
    ) -> str:
        """Generate the LLM prompt for semantic matching."""
        if entity_type in [EntityType.COVERAGE, EntityType.SECTION_COVERAGE]:
            entity_label = "coverages"
        else:
            entity_label = "exclusions"

        context_note = ""
        if entity_type in [EntityType.SECTION_COVERAGE, EntityType.SECTION_EXCLUSION]:
            context_note = "(Note: This is raw extracted data from specific document sections, not finalized effective results.)"

        return f"""You are an insurance policy expert. Your task is to match {entity_label} between two insurance documents.

Document 1 (Base/Expiring Policy) {entity_label}:
{json.dumps(doc1_entities, indent=2)}

Document 2 (Endorsement/Renewal Policy) {entity_label}:
{json.dumps(doc2_entities, indent=2)}

For each pair that represents the SAME {entity_label[:-1]} (even if with different wording or minor variations), provide a match.

Rules:
1. "match" = Same {entity_label[:-1]} with identical or nearly identical meaning
2. "partial_match" = Same {entity_label[:-1]} but with meaningful differences in terms, limits, or scope
3. Do NOT match different {entity_label}

Return a JSON array of matches:
[
  {{
    "doc1_index": <index from doc1>,
    "doc2_index": <index from doc2>,
    "match_type": "match" | "partial_match",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
  }}
]

Only include valid matches. Return empty array [] if no matches found.
"""
