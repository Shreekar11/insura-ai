from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.database.models import VectorEmbedding


class VectorEmbeddingRepository(BaseRepository[VectorEmbedding]):
    """Repository for vector embeddings with hybrid search capabilities.
    
    Improvements:
    1. Hybrid search (semantic + keyword)
    2. Advanced filtering with scoring
    3. Multi-vector search
    4. Distance thresholds
    5. Batch operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with the VectorEmbedding model."""
        super().__init__(session, VectorEmbedding)

    async def get_by_document(self, document_id: UUID) -> List[VectorEmbedding]:
        """Get all embeddings for a specific document."""
        return await self.get_all(filters={"document_id": document_id})

    async def semantic_search(
        self, 
        embedding: List[float], 
        top_k: int = 5,
        document_id: Optional[UUID] = None,
        section_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        max_distance: Optional[float] = None
    ) -> List[VectorEmbedding]:
        """Semantic search with distance filtering.
        
        Args:
            embedding: Query embedding vector (384 dimensions)
            top_k: Number of results to return
            document_id: Optional document scope filter
            section_type: Optional section type scope filter
            filters: Optional additional metadata filters
            max_distance: Optional maximum cosine distance threshold
            
        Returns:
            List of VectorEmbedding records ordered by relevance
        """
        query = select(self.model)
        
        # Apply standard filters
        if document_id:
            query = query.where(self.model.document_id == document_id)
        if section_type:
            if isinstance(section_type, list):
                query = query.where(self.model.section_type.in_(section_type))
            else:
                query = query.where(self.model.section_type == section_type)
            
        # Apply extra combined filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)
        
        # Calculate and order by cosine distance
        distance_expr = self.model.embedding.cosine_distance(embedding)
        
        # Apply distance threshold if specified
        if max_distance is not None:
            query = query.where(distance_expr <= max_distance)
        
        query = query.order_by(distance_expr)
        query = query.limit(top_k)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def hybrid_search(
        self,
        embedding: List[float],
        keyword: Optional[str] = None,
        top_k: int = 5,
        semantic_weight: float = 0.7,
        document_id: Optional[UUID] = None,
        section_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[VectorEmbedding, float]]:
        """Hybrid search combining semantic similarity and keyword matching.
        
        Args:
            embedding: Query embedding vector
            keyword: Optional keyword for text matching
            top_k: Number of results
            semantic_weight: Weight for semantic score (0-1), keyword gets (1-weight)
            document_id: Optional document filter
            section_type: Optional section type filter
            filters: Additional filters
            
        Returns:
            List of (embedding, combined_score) tuples
        """
        # Get semantic results with scores
        semantic_results = await self.semantic_search(
            embedding=embedding,
            top_k=top_k * 2,  # Get more for merging
            document_id=document_id,
            section_type=section_type,
            filters=filters
        )
        
        if not keyword:
            # No keyword, return semantic results with normalized scores
            return [(r, 1.0 - (i * 0.05)) for i, r in enumerate(semantic_results[:top_k])]
        
        # Calculate hybrid scores
        scored_results = []
        
        for idx, result in enumerate(semantic_results):
            # Semantic score (normalized by position)
            semantic_score = 1.0 - (idx / len(semantic_results))
            
            # Keyword score (based on text matching)
            keyword_score = self._calculate_keyword_score(result, keyword)
            
            # Combined score
            combined_score = (
                semantic_weight * semantic_score + 
                (1 - semantic_weight) * keyword_score
            )
            
            scored_results.append((result, combined_score))
        
        # Sort by combined score and return top K
        scored_results.sort(key=lambda x: x[1], reverse=True)
        return scored_results[:top_k]

    def _calculate_keyword_score(self, embedding: VectorEmbedding, keyword: str) -> float:
        """Calculate keyword matching score for an embedding.
        
        Args:
            embedding: Vector embedding record
            keyword: Keyword to match
            
        Returns:
            Keyword match score (0-1)
        """
        keyword_lower = keyword.lower()
        score = 0.0
        
        # Check section_type match
        if embedding.section_type and keyword_lower in embedding.section_type.lower():
            score += 0.2
        
        return min(score, 1.0)

    async def multi_vector_search(
        self,
        embeddings: List[List[float]],
        top_k: int = 5,
        aggregation: str = "average",
        **kwargs
    ) -> List[VectorEmbedding]:
        """Search using multiple query vectors and aggregate results.
        
        Useful for complex queries that can be represented by multiple vectors.
        
        Args:
            embeddings: List of query embedding vectors
            top_k: Number of final results
            aggregation: How to combine scores ("average", "min", "max")
            **kwargs: Additional search filters
            
        Returns:
            List of VectorEmbedding records with aggregated relevance
        """
        all_results = {}  # {embedding_id: [distances]}
        
        # Search with each vector
        for embedding in embeddings:
            results = await self.semantic_search(
                embedding=embedding,
                top_k=top_k * 2,  # Get more for aggregation
                **kwargs
            )
            
            # Store distances
            for idx, result in enumerate(results):
                result_id = result.id
                # Approximate distance from position (lower is better)
                distance = idx / len(results)
                
                if result_id not in all_results:
                    all_results[result_id] = []
                all_results[result_id].append(distance)
        
        # Aggregate scores
        aggregated = []
        for result_id, distances in all_results.items():
            if aggregation == "average":
                score = sum(distances) / len(distances)
            elif aggregation == "min":
                score = min(distances)
            elif aggregation == "max":
                score = max(distances)
            else:
                score = sum(distances) / len(distances)
            
            aggregated.append((result_id, score))
        
        # Sort by aggregated score
        aggregated.sort(key=lambda x: x[1])
        
        # Fetch top K results
        top_ids = [result_id for result_id, _ in aggregated[:top_k]]
        
        query = select(self.model).where(self.model.id.in_(top_ids))
        result = await self.session.execute(query)
        results = list(result.scalars().all())
        
        # Sort results to match top_ids order
        results_dict = {r.id: r for r in results}
        return [results_dict[rid] for rid in top_ids if rid in results_dict]

    async def search_by_section_similarity(
        self,
        source_section_id: str,
        top_k: int = 5,
        same_document: bool = False,
        different_document_only: bool = False
    ) -> List[VectorEmbedding]:
        """Find similar sections based on an existing section's embedding.
        
        Useful for finding comparable sections across documents.
        
        Args:
            source_section_id: Entity ID of the source section
            top_k: Number of similar sections to return
            same_document: Restrict to same document
            different_document_only: Exclude same document
            
        Returns:
            List of similar VectorEmbedding records
        """
        # Get source embedding
        source_query = select(self.model).where(self.model.entity_id == source_section_id)
        source_result = await self.session.execute(source_query)
        source = source_result.scalar_one_or_none()
        
        if not source:
            return []
        
        # Build search query
        query = select(self.model)
        query = query.where(self.model.id != source.id)  # Exclude source itself
        
        if same_document:
            query = query.where(self.model.document_id == source.document_id)
        elif different_document_only:
            query = query.where(self.model.document_id != source.document_id)
        
        # Order by similarity to source
        query = query.order_by(
            self.model.embedding.cosine_distance(source.embedding)
        )
        query = query.limit(top_k)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_embeddings_with_distance(
        self,
        embedding: List[float],
        document_id: Optional[UUID] = None,
        max_distance: float = 0.5,
        section_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Tuple[VectorEmbedding, float]]:
        """Get embeddings within a distance threshold with actual distances.
        
        Args:
            embedding: Query embedding vector
            document_id: Optional document filter
            max_distance: Maximum cosine distance (0-2, lower is more similar)
            section_type: Optional section type filter
            entity_id: Optional entity ID filter
            limit: Optional limit on number of results
            
        Returns:
            List of (embedding, distance) tuples
        """
        # Build base query
        query = select(
            self.model,
            self.model.embedding.cosine_distance(embedding).label('distance')
        )
        
        if document_id:
            query = query.where(self.model.document_id == document_id)
        if section_type:
            if isinstance(section_type, list):
                query = query.where(self.model.section_type.in_(section_type))
            else:
                query = query.where(self.model.section_type == section_type)
        if entity_id:
            query = query.where(self.model.entity_id == entity_id)
        
        # Apply distance threshold
        query = query.where(
            self.model.embedding.cosine_distance(embedding) <= max_distance
        )
        
        # Order by distance
        query = query.order_by('distance')
        
        if limit:
            query = query.limit(limit)
        
        result = await self.session.execute(query)
        return [(row.VectorEmbedding, row.distance) for row in result]

    async def batch_search(
        self,
        queries: List[Tuple[List[float], Dict[str, Any]]],
        top_k: int = 5
    ) -> List[List[VectorEmbedding]]:
        """Perform batch search for multiple queries efficiently.
        
        Args:
            queries: List of (embedding, filters) tuples
            top_k: Results per query
            
        Returns:
            List of result lists, one per query
        """
        results = []
        
        for embedding, filters in queries:
            query_results = await self.semantic_search(
                embedding=embedding,
                top_k=top_k,
                **filters
            )
            results.append(query_results)
        
        return results

    async def delete_by_document(self, document_id: UUID) -> int:
        """Delete all embeddings for a document."""
        from sqlalchemy import delete
        
        query = delete(self.model).where(self.model.document_id == document_id)
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount

    async def get_embedding_statistics(
        self,
        document_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get statistics about embeddings in the database.
        
        Args:
            document_id: Optional document to get stats for
            
        Returns:
            Dictionary with statistics
        """
        query = select(func.count(self.model.id))
        
        if document_id:
            query = query.where(self.model.document_id == document_id)
        
        result = await self.session.execute(query)
        total_count = result.scalar()
        
        # Count by section type
        section_query = select(
            self.model.section_type,
            func.count(self.model.id)
        ).group_by(self.model.section_type)
        
        if document_id:
            section_query = section_query.where(self.model.document_id == document_id)
        
        section_result = await self.session.execute(section_query)
        section_counts = {row[0]: row[1] for row in section_result}
        
        return {
            "total_embeddings": total_count,
            "by_section_type": section_counts
        }