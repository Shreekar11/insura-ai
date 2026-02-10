import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.schemas.query import MergedResult, GraphTraversalResult

LOGGER = logging.getLogger(__name__)


class ResultMergerService:
    """
    Merges results from vector retrieval and graph traversal into a unified list.
    
    Responsibilities:
    1. Deduplicate results by (document_id, entity_id).
    2. Merge content and metadata from both sources.
    3. Apply scoring logic (boost results found in both sources).
    4. Handle content priority (prefer vector content > graph properties).
    """

    def merge(
        self,
        vector_results: List[Dict[str, Any]],
        graph_results: List[GraphTraversalResult],
    ) -> List[MergedResult]:
        """
        Merge vector and graph results into a single list of MergedResult objects.

        Args:
            vector_results: List of vector search results (dicts from VectorRetrievalService).
            graph_results: List of graph traversal results.

        Returns:
            List of unique MergedResult objects sorted by relevance score.
        """
        merged_map: Dict[str, MergedResult] = {}
        
        # 1. Process Vector Results
        for v_res in vector_results:
            try:
                doc_id = v_res.get("document_id")
                entity_id = v_res.get("entity_id")
                
                if not doc_id or not entity_id:
                    LOGGER.warning(f"Vector result missing keys: doc_id={doc_id}, entity_id={entity_id}")
                    continue

                key = self._generate_key(doc_id, entity_id)

                merged_result = MergedResult(
                    source="vector",
                    content=str(v_res.get("content", "")),  # FIX: 'content', not 'evidence'
                    summary=None,
                    entity_type=v_res.get("entity_type"),
                    entity_id=entity_id,
                    canonical_entity_id=v_res.get("canonical_entity_id"),
                    section_type=v_res.get("section_type"),
                    relevance_score=v_res.get("final_score", 0.0), # FIX: 'final_score', not 'relevance_score'
                    distance=None,
                    document_id=doc_id if isinstance(doc_id, UUID) else UUID(doc_id),
                    document_name=v_res.get("document_name", "Unknown Document"),
                    page_numbers=v_res.get("page_numbers", []),
                    relationship_path=None
                )
                merged_map[key] = merged_result
            except Exception as e:
                LOGGER.warning(f"Error processing vector result: {e}", exc_info=True)

        # 2. Process Graph Results
        for g_res in graph_results:
            try:
                # Skip if no document_id (cannot cite)
                if not g_res.document_id:
                    continue
                    
                key = self._generate_key(str(g_res.document_id), g_res.entity_id)
                
                if key in merged_map:
                    # Merge Logic: Found in both sources
                    existing = merged_map[key]
                    existing.source = "both"
                    # Boost score for multi-source confirmation
                    existing.relevance_score = max(existing.relevance_score, g_res.relevance_score) + 0.1
                    existing.distance = g_res.distance
                    existing.relationship_path = g_res.relationship_chain
                    
                    # Update metadata if missing
                    if not existing.canonical_entity_id and g_res.canonical_entity_id:
                        existing.canonical_entity_id = g_res.canonical_entity_id
                        
                else:
                    # New Graph-only result
                    content = self._construct_content_from_properties(g_res)
                    
                    merged_result = MergedResult(
                        source="graph",
                        content=content,
                        summary=None,
                        entity_type=g_res.entity_type,
                        entity_id=g_res.entity_id,
                        canonical_entity_id=g_res.canonical_entity_id,
                        section_type=g_res.source_section,
                        relevance_score=g_res.relevance_score,
                        distance=g_res.distance,
                        document_id=g_res.document_id,
                        document_name="Unknown Document",
                        page_numbers=[],
                        relationship_path=g_res.relationship_chain
                    )
                    merged_map[key] = merged_result
            except Exception as e:
                LOGGER.warning(f"Error processing graph result: {e}", exc_info=True)

        # 3. Sort by relevance score
        results = list(merged_map.values())
        # Sort desc by score
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return results

    def _generate_key(self, doc_id: str, entity_id: str) -> str:
        """Generate a unique key for deduplication."""
        return f"{doc_id}_{entity_id}"

    def _construct_content_from_properties(self, node: GraphTraversalResult) -> str:
        """
        Construct a text representation of a graph node from its properties.
        Useful for nodes that don't have associated full text (e.g., sparse Exclusions).
        """
        props = node.properties
        lines = []
        if node.entity_type:
             lines.append(f"Entity Type: {node.entity_type}")
        
        # Priority fields to show first
        priority_fields = ["name", "title", "description", "limit", "deductible", "value", "address", "text", "content"]
        
        for field in priority_fields:
            if field in props and props[field]:
                lines.append(f"{field.capitalize()}: {props[field]}")
                
        # Add remaining fields, excluding internal/technical fields
        exclude_fields = set(priority_fields) | {
            "id", "entity_id", "workflow_id", "canonical_entity_id", "embedding", "vector", 
            "created_at", "updated_at", "chunk_index"
        }
        
        for k, v in props.items():
            if k not in exclude_fields and v:
                lines.append(f"{k}: {v}")
                
        return "\n".join(lines)
