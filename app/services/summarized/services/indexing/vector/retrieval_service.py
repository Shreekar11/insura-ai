from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from sentence_transformers import SentenceTransformer
import numpy as np
import re
from datetime import datetime

from app.services.base_service import BaseService
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.services.summarized.services.vector_template_service import VectorTemplateService
from app.services.summarized.services.intent_classifier_service import IntentClassifierService
from app.services.summarized.constants import (
    DOMAIN_KEYWORDS, 
    TERM_MAPPINGS, 
    QUERY_SECTION_MAPPINGS, 
    GENERAL_SECTION_BOOST
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class RetrievalService(BaseService):
    """Service for high-precision semantic retrieval of insurance documents.
    
    Improvements:
    1. Query expansion and reformulation
    2. Hybrid search (semantic + keyword)
    3. Multi-stage retrieval with reranking
    4. Context-aware filtering
    5. Relevance scoring with multiple signals
    6. Query preprocessing for insurance domain
    """

    def __init__(self, session):
        """Initialize retrieval service."""
        super().__init__(VectorEmbeddingRepository(session))
        self.vector_repo = self.repository
        self.section_repo = SectionExtractionRepository(session)
        self.template_service = VectorTemplateService()
        self.intent_classifier = IntentClassifierService()
        self.model_name = "all-MiniLM-L6-v2"
        self._model = None
        
        # Insurance domain constants
        self.domain_keywords = DOMAIN_KEYWORDS
        self.term_mappings = TERM_MAPPINGS
        self.query_section_mappings = QUERY_SECTION_MAPPINGS
        self.general_section_boost = GENERAL_SECTION_BOOST

    @property
    def model(self) -> SentenceTransformer:
        """Lazy loader for the SentenceTransformer model."""
        if self._model is None:
            LOGGER.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def preprocess_query(self, query: str) -> str:
        """Preprocess query for better insurance domain understanding.
        
        Args:
            query: Raw query string
            
        Returns:
            Preprocessed query string
        """
        query = query.strip().lower()
        
        # Expand insurance abbreviations
        for abbrev, expansions in self.term_mappings.items():
            pattern = rf"\b{re.escape(abbrev)}\b"
            if re.search(pattern, query, re.IGNORECASE):
                query = f"{query} {expansions[0]}"
        
        return query

    def expand_query(self, query: str) -> List[str]:
        """Generate query variations for better recall.
        
        Args:
            query: Original query
            
        Returns:
            List of query variations including original
        """
        queries = [query]
        query_lower = query.lower()
        
        # Add domain-specific expansions
        for keyword, related in self.domain_keywords.items():
            if keyword in query_lower:
                for related_term in related[:2]:  # Limit to top 2
                    expanded = query.replace(keyword, related_term)
                    if expanded != query:
                        queries.append(expanded)
        
        return queries[:3]  # Limit total variations

    async def multi_query_retrieval(
        self,
        queries: List[str],
        top_k: int = 10,
        **kwargs
    ) -> List[Tuple[Any, float]]:
        """Retrieve results for multiple query variations and merge with true distances.
        
        Returns:
            Merged list of (match, similarity) tuples
        """
        all_results = []
        seen_ids = set()
        
        # Extract filters for the repository call
        document_id = kwargs.get('document_id')
        section_type = kwargs.get('section_type')
        
        for query in queries:
            query_vector = self.model.encode(query).tolist()
            
            # Use get_embeddings_with_distance to get raw similarity
            # Threshold is high (0.7) to allow boosting of marginal semantic matches
            matches_with_dist = await self.vector_repo.get_embeddings_with_distance(
                embedding=query_vector,
                document_id=document_id,
                section_type=section_type,
                max_distance=0.7
            )
            
            # Limit per query variation
            for match, distance in matches_with_dist[:top_k]:
                match_id = (match.document_id, match.entity_id, match.section_type)
                if match_id not in seen_ids:
                    seen_ids.add(match_id)
                    # Convert distance to similarity (0-1)
                    similarity = max(0, 1.0 - float(distance))
                    all_results.append((match, similarity))
        
        return all_results

    def calculate_relevance_score(
        self,
        match: Any,
        query: str,
        cosine_score: float,
        filters: Optional[Dict[str, Any]] = None
    ) -> float:
        """Calculate comprehensive relevance score using multiple signals.
        
        Args:
            match: Vector embedding match
            query: Original query
            cosine_score: Base cosine similarity score
            filters: Applied filters
            
        Returns:
            Combined relevance score (0-1)
        """
        score = cosine_score
        query_lower = query.lower()
        
        # Boost 1: Query-specific section type relevance
        section_type = match.section_type
        for query_term, section_boosts in self.query_section_mappings.items():
            if query_term in query_lower:
                boost = section_boosts.get(section_type, 0.0)
                score += boost
                if boost != 0:
                    LOGGER.debug(
                        f"Section boost applied: query_term='{query_term}', "
                        f"section='{section_type}', boost={boost}"
                    )
        
        # Boost 2: General section type importance (fallback)
        score += self.general_section_boost.get(section_type, 0.0)
        
        # Boost 3: Keyword matching in searchable attributes
        searchable_text = []
        
        # Add section_type
        if hasattr(match, 'section_type') and match.section_type:
            searchable_text.append(str(match.section_type))
        
        # Add entity_type
        if hasattr(match, 'entity_type') and match.entity_type:
            searchable_text.append(str(match.entity_type))
        
        # Add location_id
        if hasattr(match, 'location_id') and match.location_id:
            searchable_text.append(str(match.location_id))
        
        # Add workflow_type
        if hasattr(match, 'workflow_type') and match.workflow_type:
            searchable_text.append(str(match.workflow_type))
        
        if searchable_text:
            combined_text = " ".join(searchable_text).lower()
            # Split query by spaces and common separators
            query_words = query_lower.replace("/", " ").replace("-", " ").split()
            keyword_matches = sum(1 for word in query_words 
                                 if len(word) > 2 and word in combined_text)
            
            # Additional exact term boosts
            if "policy" in query_lower and "policy" in combined_text:
                score += 0.05
            if "coverage" in query_lower and "coverage" in combined_text:
                score += 0.05
            
            score += keyword_matches * 0.03
        
        # Boost 4: Recency (if effective_date available)
        if hasattr(match, 'effective_date') and match.effective_date:
            try:
                days_old = (datetime.now().date() - match.effective_date).days
                if days_old < 365:  # Within last year
                    recency_boost = 0.05 * (1 - days_old / 365)
                    score += recency_boost
            except (TypeError, AttributeError):
                pass  # Skip if date comparison fails
        
        # Boost 5: Filter alignment
        if filters:
            if filters.get("document_id") == match.document_id:
                score += 0.02  # Reward document-scoped searches
            if filters.get("section_type") == match.section_type:
                score += 0.03  # Reward section-scoped searches
        
        return min(score, 1.0)  # Cap at 1.0

    def rerank_results(
        self,
        results: List[Tuple[Any, float]],
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Any, float]]:
        """Rerank results using true base similarity and section boosts.
        
        Args:
            results: List of (match, base_similarity) tuples
            query: Original query
            filters: Applied filters
            
        Returns:
            List of (result, final_score) tuples sorted by relevance
        """
        scored_results = []
        
        for match, base_similarity in results:
            relevance_score = self.calculate_relevance_score(
                match=match,
                query=query,
                cosine_score=base_similarity,
                filters=filters
            )
            
            scored_results.append((match, relevance_score))
        
        # Sort by relevance score descending
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        return scored_results

    async def run(
        self, 
        query: str, 
        top_k: int = 5,
        document_id: Optional[UUID] = None,
        section_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_query_expansion: bool = True,
        rerank: bool = True,
        include_entity_data: bool = True
    ) -> List[Dict[str, Any]]:
        """Retrieval with multiple accuracy improvements.
        
        Args:
            query: Natural language question or search term
            top_k: Number of final results to return
            document_id: Optional document scope filter
            section_type: Optional section type filter
            filters: Additional metadata filters
            use_query_expansion: Enable query expansion
            rerank: Enable result reranking
            include_entity_data: Fetch actual entity data for results
            
        Returns:
            List of relevant results with scores and metadata
        """
        LOGGER.info(f"Retrieval query: '{query}' (top_k={top_k})")
        
        # Step 1: Preprocess query
        processed_query = self.preprocess_query(query)
        
        # Step 2: Query intent classification (if section_type NOT explicitly provided)
        # Filter is applied ONLY if user didn't specify a section_type
        allowed_sections = None
        if not section_type:
            allowed_sections = self.intent_classifier.classify(processed_query)
            if allowed_sections:
                LOGGER.info(f"Intent-based filtering applied: {allowed_sections}")
        
        # Step 3: Query expansion (if enabled)
        if use_query_expansion:
            query_variations = self.expand_query(processed_query)
            LOGGER.debug(f"Query variations: {query_variations}")
        else:
            query_variations = [processed_query]
        
        # Step 4: Multi-query retrieval
        filter_kwargs = {}
        if document_id:
            filter_kwargs['document_id'] = document_id
        
        # Use intent-based sections ONLY if explict section_type wasn't provided
        filter_kwargs['section_type'] = section_type or allowed_sections
        
        if filters:
            filter_kwargs['filters'] = filters
        
        # Retrieve significantly more results for reranking pool (Precision over throughput)
        initial_top_k = top_k * 10 if rerank else top_k
        
        matches = await self.multi_query_retrieval(
            queries=query_variations,
            top_k=initial_top_k,
            **filter_kwargs
        )
        
        LOGGER.info(f"Retrieved {len(matches)} initial matches for {len(query_variations)} variations")
        if not matches:
             LOGGER.warning(f"No semantic matches found for any query variation of: '{query}'")
        
        # Step 4: Rerank results (if enabled)
        if rerank and matches:
            scored_matches = self.rerank_results(
                results=matches,
                query=query,
                filters={'document_id': document_id, 'section_type': section_type}
            )
            # Take top K after reranking
            final_matches = [match for match, score in scored_matches[:top_k]]
            match_scores = {id(match): score for match, score in scored_matches[:top_k]}
        else:
            final_matches = matches[:top_k]
            match_scores = {id(match): 1.0 for match in final_matches}
        
        # Step 5: Format results with enhanced metadata
        results = []
        for match in final_matches:
            # Safely extract metadata fields
            effective_date = None
            if hasattr(match, 'effective_date') and match.effective_date:
                try:
                    effective_date = str(match.effective_date)
                except Exception:
                    pass
            
            location_id = getattr(match, 'location_id', None)
            workflow_type = getattr(match, 'workflow_type', None)
            
            # Step 7: Normalized response format (Answer, Evidence, Confidence)
            # Re-mapping fields for deterministic answer extraction
            relevance_score = match_scores.get(id(match), 0.0)
            
            # Extract content preview for evidence
            evidence = await self._get_content_preview(match)
            
            # Fetch entity data for structured answer
            entity_data = None
            if include_entity_data:
                entity_data = await self._fetch_entity_data(match)

            result = {
                "document_id": str(match.document_id),
                "section_type": match.section_type or "unknown",
                "entity_type": match.entity_type or "unknown",
                "entity_id": match.entity_id or "unknown",
                "relevance_score": relevance_score,
                "metadata": {
                    "effective_date": effective_date,
                    "location_id": location_id,
                    "workflow_type": workflow_type,
                },
                # New standard response fields
                "answer": entity_data,
                "evidence": evidence,
                "confidence": "high" if relevance_score > 0.8 else "medium" if relevance_score > 0.6 else "low",
                
                # Keep legacy fields for compatibility during transition
                "entity_data": entity_data,
            }
            
            results.append(result)
        
        LOGGER.info(f"Returning {len(results)} final results")
        return results
    
    async def _fetch_entity_data(self, match: Any) -> Optional[Dict[str, Any]]:
        """Fetch the actual extracted entity data for a match from section extractions.
        
        Args:
            match: Vector embedding match
            
        Returns:
            Dictionary of entity data or None
        """
        try:
            section_type = match.section_type
            entity_id = match.entity_id
            document_id = match.document_id
            
            # Since embeddings are derived from SectionExtraction.extracted_fields,
            # we fetch the section extraction record first.
            sections = await self.section_repo.get_by_document(document_id, UUID(match.workflow_type) if match.workflow_type else None, section_type)
            if not sections:
                # Fallback: get by document_id and section_type only if workflow_type is missing
                from sqlalchemy import select
                from app.database.models import SectionExtraction
                stmt = select(SectionExtraction).where(
                    SectionExtraction.document_id == document_id,
                    SectionExtraction.section_type == section_type
                )
                res = await self.repository.session.execute(stmt)
                sections = list(res.scalars().all())

            if not sections:
                return None

            # For root sections, return the fields directly
            section = sections[0]
            data = section.extracted_fields

            if entity_id.endswith("_section_root"):
                return data

            # For nested entities (coverages, claims, locations, etc.), find the specific one
            if section_type.lower() == "coverages" and "coverages" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["coverages"]):
                        return data["coverages"][idx]
            
            elif section_type.lower() == "loss_run" and "claims" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["claims"]):
                        return data["claims"][idx]

            elif section_type.lower() == "schedule_of_values" and "locations" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["locations"]):
                        return data["locations"][idx]

            elif section_type.lower() == "endorsements" and "endorsements" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["endorsements"]):
                        return data["endorsements"][idx]

            elif section_type.lower() == "exclusions" and "exclusions" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["exclusions"]):
                        return data["exclusions"][idx]

            elif section_type.lower() == "definitions" and "definitions" in data:
                idx_str = entity_id.split("_")[-1]
                if idx_str.isdigit():
                    idx = int(idx_str)
                    if 0 <= idx < len(data["definitions"]):
                        return data["definitions"][idx]

            return data  # Default return generic section data
            
        except Exception as e:
            LOGGER.warning(f"Failed to fetch entity data: {e}")
        
        return None

    async def _get_content_preview(self, match: Any, max_chars: int = 500) -> Optional[str]:
        """Extract content preview from match by regenerating template.
        
        Since we don't store embedded_text (per architecture), we need to:
        1. Fetch the source entity data
        2. Regenerate the template
        3. Return preview
        
        Args:
            match: Vector embedding match
            max_chars: Maximum preview length
            
        Returns:
            Content preview string or None
        """
        try:
            entity_data = await self._fetch_entity_data(match)
            if not entity_data:
                return f"Section: {match.section_type} | ID: {match.entity_id}"

            # Regenerate template text
            preview = await self.template_service.run(match.section_type, entity_data)
            
            if preview and len(preview) > max_chars:
                preview = preview[:max_chars] + "..."
            
            return preview
        except Exception as e:
            LOGGER.warning(f"Failed to generate content preview: {e}")
            return f"Section: {match.section_type} | ID: {match.entity_id}"

    async def search_with_context(
        self,
        query: str,
        document_id: UUID,
        top_k: int = 5,
        context_window: int = 2
    ) -> List[Dict[str, Any]]:
        """Retrieve results with surrounding context sections.
        
        Useful for understanding the broader context around matches.
        
        Args:
            query: Search query
            document_id: Document to search within
            top_k: Number of primary results
            context_window: Number of adjacent sections to include
            
        Returns:
            Results with context sections included
        """
        # Get primary results
        primary_results = await self.run(
            query=query,
            top_k=top_k,
            document_id=document_id
        )
        
        # For each result, fetch adjacent sections
        # This would require additional repository methods
        # Placeholder for now
        
        return primary_results