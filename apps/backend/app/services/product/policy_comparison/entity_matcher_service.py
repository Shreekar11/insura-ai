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
        endorsement_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """Match entities between two documents.

        Args:
            doc1_entities: List of entities from document 1 (base/expiring)
            doc2_entities: List of entities from document 2 (endorsement/renewal)
            entity_type: Type of entity (coverage or exclusion)
            endorsement_mode: If True, doc2 is an endorsement that only contains modifications.
                            Unmatched doc1 entities are marked as UNCHANGED instead of REMOVED.

        Returns:
            List of match results with match_type, confidence, and entity references
        """
        LOGGER.info(
            f"Matching {len(doc1_entities)} doc1 {entity_type.value}s with {len(doc2_entities)} doc2 {entity_type.value}s"
        )

        matches = []
        matched_doc1_indices = set()
        matched_doc2_indices = set()

        # Phase 1: Canonical ID matching
        canonical_matches = self._match_by_canonical_id(
            doc1_entities, doc2_entities, entity_type
        )

        for match in canonical_matches:
            matches.append(match)
            if match.get("doc1_index") is not None:
                matched_doc1_indices.add(match["doc1_index"])
            if match.get("doc2_index") is not None:
                matched_doc2_indices.add(match["doc2_index"])

        # Phase 2: LLM semantic matching for unmatched entities
        unmatched_doc1 = [
            (i, e) for i, e in enumerate(doc1_entities)
            if i not in matched_doc1_indices
        ]
        unmatched_doc2 = [
            (i, e) for i, e in enumerate(doc2_entities)
            if i not in matched_doc2_indices
        ]

        if unmatched_doc1 or unmatched_doc2:
            llm_matches = await self._match_by_llm(
                unmatched_doc1, unmatched_doc2, entity_type
            )

            for match in llm_matches:
                matches.append(match)
                if match.get("doc1_index") is not None:
                    matched_doc1_indices.add(match["doc1_index"])
                if match.get("doc2_index") is not None:
                    matched_doc2_indices.add(match["doc2_index"])

        # Phase 3: Mark remaining unmatched entities
        # In endorsement mode, unmatched doc1 entities are UNCHANGED (not modified by endorsement)
        # In standard mode, unmatched doc1 entities are REMOVED
        for i, entity in enumerate(doc1_entities):
            if i not in matched_doc1_indices:
                if endorsement_mode:
                    # Endorsement didn't modify this entity - it remains unchanged from base
                    matches.append({
                        "match_type": MatchType.UNCHANGED,
                        "doc1_index": i,
                        "doc1_entity": entity,
                        "doc2_index": None,
                        "doc2_entity": None,
                        "confidence": Decimal("1.0"),
                        "match_method": "endorsement_unmodified",
                        "reasoning": f"Base {entity_type.value} not modified by endorsement",
                    })
                else:
                    # Standard comparison - entity was removed in doc2
                    matches.append({
                        "match_type": MatchType.REMOVED,
                        "doc1_index": i,
                        "doc1_entity": entity,
                        "doc2_index": None,
                        "doc2_entity": None,
                        "confidence": Decimal("1.0"),
                        "match_method": "unmatched",
                        "reasoning": f"No corresponding {entity_type.value} found in document 2",
                    })

        for i, entity in enumerate(doc2_entities):
            if i not in matched_doc2_indices:
                matches.append({
                    "match_type": MatchType.ADDED,
                    "doc1_index": None,
                    "doc1_entity": None,
                    "doc2_index": i,
                    "doc2_entity": entity,
                    "confidence": Decimal("1.0"),
                    "match_method": "unmatched",
                    "reasoning": f"New {entity_type.value} in document 2",
                })

        LOGGER.info(f"Matching complete: {len(matches)} total matches")
        return matches

    def _match_by_canonical_id(
        self,
        doc1_entities: List[Dict[str, Any]],
        doc2_entities: List[Dict[str, Any]],
        entity_type: EntityType,
    ) -> List[Dict[str, Any]]:
        """Match entities using canonical_id field."""
        matches = []

        # Build index of doc2 entities by canonical_id
        doc2_by_canonical = {}
        for i, entity in enumerate(doc2_entities):
            canonical_id = entity.get("canonical_id")
            if canonical_id:
                doc2_by_canonical[canonical_id] = (i, entity)

        for i, doc1_entity in enumerate(doc1_entities):
            canonical_id = doc1_entity.get("canonical_id")
            if canonical_id and canonical_id in doc2_by_canonical:
                j, doc2_entity = doc2_by_canonical[canonical_id]

                # Check if entities are identical or have differences
                match_type, differences = self._compare_entity_fields(
                    doc1_entity, doc2_entity, entity_type
                )

                matches.append({
                    "match_type": match_type,
                    "doc1_index": i,
                    "doc1_entity": doc1_entity,
                    "doc2_index": j,
                    "doc2_entity": doc2_entity,
                    "confidence": Decimal("0.95"),
                    "match_method": "canonical_id",
                    "field_differences": differences if differences else None,
                    "reasoning": f"Matched by canonical_id: {canonical_id}",
                })

        LOGGER.debug(f"Canonical ID matching found {len(matches)} matches")
        return matches

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
        # Define key fields to compare
        if entity_type == EntityType.COVERAGE:
            key_fields = [
                "coverage_name", "coverage_type", "limit_amount", "deductible_amount",
                "premium_amount", "effective_terms", "limits", "deductibles",
                "is_modified", "modification_details"
            ]
        else:
            key_fields = [
                "exclusion_name", "effective_state", "scope", "carve_backs",
                "conditions", "impacted_coverages", "is_modified", "modification_details"
            ]

        differences = []
        for field in key_fields:
            val1 = doc1_entity.get(field)
            val2 = doc2_entity.get(field)

            if val1 != val2 and (val1 is not None or val2 is not None):
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
        entity_label = "coverages" if entity_type == EntityType.COVERAGE else "exclusions"

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

    async def find_cross_type_matches(
        self,
        doc1_coverages: List[Dict[str, Any]],
        doc1_exclusions: List[Dict[str, Any]],
        doc2_coverages: List[Dict[str, Any]],
        doc2_exclusions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find entities representing the same insurance concept but classified as different types.

        This detects cases where the same provision is classified as Coverage in one document
        and Exclusion in the other (or vice versa), which indicates a data quality issue.

        Args:
            doc1_coverages: Coverage entities from document 1
            doc1_exclusions: Exclusion entities from document 1
            doc2_coverages: Coverage entities from document 2
            doc2_exclusions: Exclusion entities from document 2

        Returns:
            List of TYPE_RECLASSIFIED match results with both entity types recorded
        """
        LOGGER.info(
            f"Finding cross-type matches: doc1 ({len(doc1_coverages)} cov, {len(doc1_exclusions)} exc) "
            f"vs doc2 ({len(doc2_coverages)} cov, {len(doc2_exclusions)} exc)"
        )

        cross_type_matches = []

        # Check doc1 coverages vs doc2 exclusions
        if doc1_coverages and doc2_exclusions:
            matches = await self._cross_type_llm_match(
                doc1_coverages, doc2_exclusions,
                EntityType.COVERAGE, EntityType.EXCLUSION
            )
            cross_type_matches.extend(matches)

        # Check doc1 exclusions vs doc2 coverages
        if doc1_exclusions and doc2_coverages:
            matches = await self._cross_type_llm_match(
                doc1_exclusions, doc2_coverages,
                EntityType.EXCLUSION, EntityType.COVERAGE
            )
            cross_type_matches.extend(matches)

        LOGGER.info(f"Found {len(cross_type_matches)} cross-type matches")
        return cross_type_matches

    async def _cross_type_llm_match(
        self,
        doc1_entities: List[Dict[str, Any]],
        doc2_entities: List[Dict[str, Any]],
        doc1_type: EntityType,
        doc2_type: EntityType,
    ) -> List[Dict[str, Any]]:
        """Use LLM to detect cross-type matches between entities.

        Args:
            doc1_entities: Entities from document 1 (one type)
            doc2_entities: Entities from document 2 (different type)
            doc1_type: Entity type for doc1 entities
            doc2_type: Entity type for doc2 entities

        Returns:
            List of TYPE_RECLASSIFIED match results
        """
        # Simplify entity data for LLM (reduce token usage)
        simplified_doc1 = []
        for i, entity in enumerate(doc1_entities):
            name = entity.get("coverage_name") or entity.get("exclusion_name") or entity.get("name") or entity.get("title")
            desc = entity.get("description") or entity.get("scope") or ""
            simplified_doc1.append({
                "index": i,
                "name": name,
                "description": desc[:200] if desc else "",  # Truncate long descriptions
                "type": doc1_type.value,
            })

        simplified_doc2 = []
        for i, entity in enumerate(doc2_entities):
            name = entity.get("coverage_name") or entity.get("exclusion_name") or entity.get("name") or entity.get("title")
            desc = entity.get("description") or entity.get("scope") or ""
            simplified_doc2.append({
                "index": i,
                "name": name,
                "description": desc[:200] if desc else "",
                "type": doc2_type.value,
            })

        prompt = f"""You are an insurance policy expert. Find entities that represent the SAME insurance concept but are classified as different entity types.

Document 1 entities ({doc1_type.value}s):
{json.dumps(simplified_doc1, indent=2)}

Document 2 entities ({doc2_type.value}s):
{json.dumps(simplified_doc2, indent=2)}

Task: Find pairs where an entity in Document 1 and an entity in Document 2 represent the SAME insurance provision/concept, but are classified as different types.

ONLY return high-confidence matches (confidence >= 0.8) where you are certain the entities represent the same concept.

Return a JSON array:
[
  {{
    "doc1_index": <index from doc1>,
    "doc2_index": <index from doc2>,
    "confidence": <0.8-1.0>,
    "reasoning": "<brief explanation of why these represent the same concept>"
  }}
]

Return empty array [] if no high-confidence cross-type matches found.
"""

        try:
            response = await self.client.generate_content(contents=prompt)
            matches_data = parse_json_safely(response, fallback=[])

            if not isinstance(matches_data, list):
                LOGGER.warning(f"Cross-type LLM response not a list: {matches_data}")
                return []

            results = []
            for match in matches_data:
                doc1_idx = match.get("doc1_index")
                doc2_idx = match.get("doc2_index")
                confidence = match.get("confidence", 0.0)

                if doc1_idx is None or doc2_idx is None:
                    continue

                if doc1_idx >= len(doc1_entities) or doc2_idx >= len(doc2_entities):
                    LOGGER.warning(f"Invalid cross-type match indices: {doc1_idx}, {doc2_idx}")
                    continue

                results.append({
                    "match_type": MatchType.TYPE_RECLASSIFIED,
                    "doc1_index": doc1_idx,
                    "doc1_entity": doc1_entities[doc1_idx],
                    "doc1_type": doc1_type,
                    "doc2_index": doc2_idx,
                    "doc2_entity": doc2_entities[doc2_idx],
                    "doc2_type": doc2_type,
                    "confidence": Decimal(str(confidence)),
                    "match_method": "cross_type_llm",
                    "reasoning": match.get("reasoning", "Same concept classified as different entity type"),
                })

            return results

        except Exception as e:
            LOGGER.error(f"Cross-type LLM matching failed: {e}", exc_info=True)
            return []
