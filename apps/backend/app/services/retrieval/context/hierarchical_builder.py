from typing import List, Dict, Tuple
from uuid import UUID

from app.schemas.query import MergedResult, ContextPayload, ProvenanceEntry
from app.services.processed.services.chunking.token_counter import TokenCounter
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class HierarchicalContextBuilder:
    """
    Builds a hierarchical context payload from merged results within a token budget.
    
    Strategies:
    1. Prioritize highest scoring results for full-text inclusion (Top-N).
    2. Include summaries for remaining relevant results to save tokens.
    3. Maintain a provenance index for citation tracking.
    4. Respect max_context_tokens limit.
    """

    def __init__(self, token_counter: TokenCounter | None = None):
        self.token_counter = token_counter or TokenCounter()

    def build_context(
        self,
        results: List[MergedResult],
        max_tokens: int = 8000,
        top_n_full_text: int = 5,
    ) -> ContextPayload:
        """
        Assemble the context payload.

        Args:
            results: List of sorted MergedResult objects.
            max_tokens: Total token budget for the context.
            top_n_full_text: Number of top results to include as full text.

        Returns:
            ContextPayload containing full text results, summaries, and provenance.
        """
        full_text_results: List[MergedResult] = []
        summary_results: List[MergedResult] = []
        provenance_index: Dict[str, ProvenanceEntry] = {}
        
        current_tokens = 0
        citation_counter = 1
        
        effective_limit = int(max_tokens * 0.95)

        for i, result in enumerate(results):
            if current_tokens >= effective_limit:
                break

            citation_id = f"[{citation_counter}]"
            
            # Determine if this result gets full text or summary
            is_full_text = i < top_n_full_text
            
            # Prepare content
            if is_full_text:
                content_to_add = result.content
            else:
                content_to_add = result.summary or self._generate_fallback_summary(result)
                result.summary = content_to_add

            # Check token cost
            content_tokens = self.token_counter.count_tokens(content_to_add)
            overhead_tokens = 50
            cost = content_tokens + overhead_tokens
            
            if current_tokens + cost > effective_limit:
                if is_full_text:
                    # Downgrade to summary to see if it fits
                    fallback_summary = result.summary or self._generate_fallback_summary(result)
                    result.summary = fallback_summary
                    summary_cost = self.token_counter.count_tokens(fallback_summary) + overhead_tokens
                    
                    if current_tokens + summary_cost <= effective_limit:
                        is_full_text = False
                        content_to_add = fallback_summary
                        cost = summary_cost
                    else:
                        continue
                else:
                    continue

            # Add to respective list
            if is_full_text:
                full_text_results.append(result)
            else:
                summary_results.append(result)

            # Update Provenance Index
            # Keying by citation_id so the LLM generation service can look it up
            provenance_index[citation_id] = ProvenanceEntry(
                document_name=result.document_name,
                document_id=result.document_id,
                page_numbers=result.page_numbers,
                section_type=result.section_type,
                relationship_path=result.relationship_path
            )
            result.citation_id = citation_id

            current_tokens += cost
            citation_counter += 1
            
        return ContextPayload(
            full_text_results=full_text_results,
            summary_results=summary_results,
            total_results=len(results),
            token_count=current_tokens,
            provenance_index=provenance_index
        )

    def _generate_fallback_summary(self, result: MergedResult) -> str:
        """
        Generate a lightweight summary for a result if none exists.
        """
        parts = []
        if result.entity_type:
            parts.append(f"Entity: {result.entity_type}")
        if result.entity_id:
            cleaned_id = result.entity_id.split('_')[-1] if '_' in result.entity_id else result.entity_id
            parts.append(f"ID: {cleaned_id}")
            
        # Try to extract first sentence or first N chars of content
        content_snippet = result.content[:200].replace("\n", " ") + "..." if len(result.content) > 200 else result.content
        parts.append(f"Content: {content_snippet}")
        
        return " | ".join(parts)
