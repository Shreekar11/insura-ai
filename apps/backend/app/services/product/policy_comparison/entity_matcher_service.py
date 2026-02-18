"""Service for semantic matching of insurance entities across documents."""

import json
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal, InvalidOperation

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
            entity_type: Type of entities being matched
            endorsement_mode: If True, doc2 is an endorsement that only contains modifications.
                            Unmatched doc1 entities are marked as UNCHANGED instead of REMOVED.

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

        # 2. Match by exact name (deterministic fallback)
        if unmatched_doc1 and unmatched_doc2:
            name_matches, unmatched_doc1, unmatched_doc2 = self._match_by_name(
                unmatched_doc1, unmatched_doc2, entity_type
            )
            matches.extend(name_matches)

        # 3. Match remaining using LLM
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
        
        # Determine ID fields based on type. 'id' is generally safe to use as a fallback.
        id_fields = ["canonical_id", "id"]
        
        # Map for quick lookup
        doc1_id_map = {}
        for i, entity in enumerate(doc1_entities):
            for id_field in id_fields:
                val = entity.get(id_field)
                if val:
                    # Key by (id_field, val) to avoid collisions between different ID types
                    doc1_id_map[(id_field, val)] = (i, entity)

        matched_doc1_indices = set()
        matched_doc2_indices = set()
        
        for j, doc2_entity in enumerate(doc2_entities):
            match_info = None
            for id_field in id_fields:
                val = doc2_entity.get(id_field)
                if val and (id_field, val) in doc1_id_map:
                    match_info = doc1_id_map[(id_field, val)]
                    break
            
            if match_info:
                i, doc1_entity = match_info
                if i not in matched_doc1_indices: # Ensure doc1 entity is not already matched
                    match_type, differences = self._compare_entity_fields(
                        doc1_entity, doc2_entity, entity_type
                    )
                    matches.append({
                        "doc1_index": i, "doc2_index": j,
                        "match_type": match_type,
                        "doc1_entity": doc1_entity, "doc2_entity": doc2_entity,
                        "field_differences": differences,
                        "confidence": Decimal("1.0"),
                        "match_method": "canonical_id",
                    })
                    matched_doc1_indices.add(i)
                    matched_doc2_indices.add(j)

        unmatched_doc1 = [
            (i, entity) for i, entity in enumerate(doc1_entities)
            if i not in matched_doc1_indices
        ]
        unmatched_doc2 = [
            (j, entity) for j, entity in enumerate(doc2_entities) 
            if j not in matched_doc2_indices
        ]

        return matches, unmatched_doc1, unmatched_doc2

    def _match_by_name(
        self,
        unmatched_doc1: List[Tuple[int, Dict[str, Any]]],
        unmatched_doc2: List[Tuple[int, Dict[str, Any]]],
        entity_type: EntityType,
    ) -> Tuple[List[Dict[str, Any]], List[Tuple[int, Dict[str, Any]]], List[Tuple[int, Dict[str, Any]]]]:
        """Match entities by name with normalization (handling prefixes/suffixes)."""
        matches = []
        doc1_name_map = {}
        
        def normalize_name(name: str) -> str:
            if not name: return ""
            n = name.lower().strip()
            # Remove common endorsement suffixes/prefixes
            suffixes = [" - increased limit", " - reduced limit", " coverage", " - modified", " modification"]
            prefixes = ["physical damage -", "hired auto physical damage -", "additional insured -"]
            for p in prefixes:
                if n.startswith(p): 
                    n = n[len(p):].strip()
            for s in suffixes:
                if n.endswith(s): 
                    n = n[:-len(s)].strip()
            return n

        for i, entity in unmatched_doc1:
            name = self._get_entity_name(entity, entity_type)
            norm_name = normalize_name(name)
            if norm_name:
                if norm_name not in doc1_name_map:
                    doc1_name_map[norm_name] = (i, entity)

        remaining_doc2 = []
        for j, entity in unmatched_doc2:
            name = self._get_entity_name(entity, entity_type)
            norm_name = normalize_name(name)
            
            if norm_name and norm_name in doc1_name_map:
                i, doc1_entity = doc1_name_map.pop(norm_name)
                match_type, differences = self._compare_entity_fields(
                    doc1_entity, entity, entity_type
                )
                matches.append({
                    "doc1_index": i,
                    "doc2_index": j,
                    "match_type": match_type,
                    "doc1_entity": doc1_entity,
                    "doc2_entity": entity,
                    "field_differences": differences,
                    "confidence": Decimal("0.90"),
                    "match_method": "normalized_name",
                })
            else:
                # Try substring match as a last resort deterministic step
                substring_match_found = False
                if norm_name and len(norm_name) > 8:
                    for n1 in list(doc1_name_map.keys()):
                        if norm_name in n1 or n1 in norm_name:
                            i, doc1_entity = doc1_name_map.pop(n1)
                            match_type, differences = self._compare_entity_fields(
                                doc1_entity, entity, entity_type
                            )
                            matches.append({
                                "doc1_index": i, "doc2_index": j,
                                "match_type": match_type, "doc1_entity": doc1_entity, "doc2_entity": entity,
                                "field_differences": differences,
                                "confidence": Decimal("0.85"),
                                "match_method": "substring_name_match",
                            })
                            substring_match_found = True
                            break
                
                if not substring_match_found:
                    remaining_doc2.append((j, entity))

        remaining_doc1 = list(doc1_name_map.values())
        return matches, remaining_doc1, remaining_doc2

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
        # Check top level first, then attributes
        attrs = entity.get("attributes", {}) if isinstance(entity.get("attributes"), dict) else {}
        
        if entity_type == EntityType.COVERAGE:
            return entity.get("coverage_name") or attrs.get("coverage_name") or entity.get("name") or attrs.get("name") or "Unknown Coverage"
        else:
            return entity.get("exclusion_name") or attrs.get("exclusion_name") or entity.get("title") or attrs.get("title") or "Unknown Exclusion"

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
        # Define key fields and their comparison types
        # comparison_type: 'direct' (equality), 'numeric' (delta), 'text' (semantic/fuzzy), 'list' (set comparison)
        field_configs = {}
        
        if entity_type == EntityType.COVERAGE:
            field_configs = {
                "coverage_name": "direct",
                "coverage_type": "direct",
                "limit_amount": "numeric",
                "deductible_amount": "numeric",
                "premium_amount": "numeric",
                "limits": "nested_numeric",
                "deductibles": "nested_numeric",
                # Endorsement specific fields often map to existing ones
                "limit_modification": "numeric_text",
                "deductible_modification": "numeric_text",
                "scope_modification": "text",
            }
        elif entity_type == EntityType.EXCLUSION:
            field_configs = {
                "exclusion_name": "direct",
                "effective_state": "direct",
                "scope": "text",
                "carve_backs": "list",
                "conditions": "text",
                "impacted_coverages": "list",
                "scope_modification": "text",
                "impacted_exclusion": "direct",
            }
        elif entity_type == EntityType.SECTION_COVERAGE:
            field_configs = {
                "name": "direct",
                "coverage_basis": "direct",
                "coverage_category": "direct",
                "limit_aggregate": "numeric",
                "limit_per_occurrence": "numeric",
                "deductible_per_occurrence": "numeric",
                "description": "text"
            }
        elif entity_type == EntityType.SECTION_EXCLUSION:
            field_configs = {
                "title": "direct",
                "description": "text",
                "exception_carveback": "text",
                "applicability": "text",
                "impacted_sections": "list"
            }

        differences = []
        doc1_attrs = doc1_entity.get("attributes", {}) if isinstance(doc1_entity.get("attributes"), dict) else {}
        doc2_attrs = doc2_entity.get("attributes", {}) if isinstance(doc2_entity.get("attributes"), dict) else {}

        for field, comp_type in field_configs.items():
            # Check top level then attributes for both
            val1 = doc1_entity.get(field) if field in doc1_entity else doc1_attrs.get(field)
            val2 = doc2_entity.get(field) if field in doc2_entity else doc2_attrs.get(field)

            # Skip comparison if both are None
            if val1 is None and val2 is None:
                continue

            # Special case: Endorsement might carry info in a modification field 
            # that we want to compare against a base field.
            if field.endswith("_modification") and val2 and not val1:
                # If we have a modification in doc2 but nothing in doc1 context, 
                # it's a change by definition.
                differences.append({
                    "field": field,
                    "doc1_value": None,
                    "doc2_value": val2,
                    "change_type": "modified"
                })
                continue

            field_diff = self._get_field_delta(field, val1, val2, comp_type)
            if field_diff:
                differences.append(field_diff)

        if not differences:
            return MatchType.MATCH, []
        else:
            return MatchType.PARTIAL_MATCH, differences

    def _get_field_delta(self, field: str, val1: Any, val2: Any, comp_type: str) -> Optional[Dict[str, Any]]:
        """Calculate the delta between two field values based on comparison type."""
        if val1 == val2:
            return None

        if comp_type == "numeric":
            d1 = self._to_decimal(val1)
            d2 = self._to_decimal(val2)
            if d1 == d2:
                return None
            
            return {
                "field": field,
                "doc1_value": val1,
                "doc2_value": val2,
                "absolute_change": float(d2 - d1) if d1 is not None and d2 is not None else None,
                "percent_change": float((d2 - d1) / d1 * 100) if d1 and d2 and d1 != 0 else None,
                "change_type": "increase" if (d1 is not None and d2 is not None and d2 > d1) else "decrease" if (d1 is not None and d2 is not None and d2 < d1) else "modified"
            }

        if comp_type == "nested_numeric" and (isinstance(val1, dict) or isinstance(val2, dict)):
            # Flatten dicts or compare specific keys (amount, limit, etc.)
            v1 = val1.get("amount") if isinstance(val1, dict) else val1
            v2 = val2.get("amount") if isinstance(val2, dict) else val2
            return self._get_field_delta(field, v1, v2, "numeric")

        if comp_type == "numeric_text":
            # Attempt to extract number from string (e.g., "$50 per day")
            d1 = self._extract_number(val1)
            d2 = self._extract_number(val2)
            if d1 is not None and d2 is not None:
                return self._get_field_delta(field, d1, d2, "numeric")
            # Fallback to direct string comparison
            if str(val1) != str(val2):
                return {"field": field, "doc1_value": val1, "doc2_value": val2, "change_type": "modified"}

        # Default string comparison
        if str(val1) != str(val2):
            return {
                "field": field,
                "doc1_value": val1,
                "doc2_value": val2,
                "change_type": "modified"
            }
        
        return None

    def _to_decimal(self, value: Any) -> Optional[Decimal]:
        """Convert a value to Decimal for calculation."""
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        if isinstance(value, str):
            # Clean up string ($ , %)
            clean_val = value.replace('$', '').replace(',', '').strip()
            try:
                return Decimal(clean_val)
            except (InvalidOperation, ValueError):
                return None
        return None

    def _extract_number(self, value: Any) -> Optional[Decimal]:
        """Extract the first number found in a string."""
        if value is None: return None
        if isinstance(value, (int, float, Decimal)): return Decimal(str(value))
        if not isinstance(value, str): return None
        
        import re
        match = re.search(r"(\d+(\.\d+)?)", value.replace(',', ''))
        if match:
            return Decimal(match.group(1))
        return None

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
            matches_data = parse_json_safely(response) or []

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
