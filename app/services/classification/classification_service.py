"""Classification service for document classification using aggregated chunk signals.

This service aggregates per-chunk classification signals to determine the
overall document type. It uses weighted aggregation with configurable
thresholds and optional fallback classification.
"""

from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from app.services.classification.constants import (
    DOCUMENT_TYPES,
    ACCEPT_THRESHOLD,
    REVIEW_THRESHOLD,
    DEFAULT_CHUNK_WEIGHT,
    FIRST_PAGE_WEIGHT,
    DECLARATIONS_PAGE_WEIGHT,
    KEYWORD_MULTIPLIERS,
    MIN_CONFIDENCE,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ClassificationService:
    """Service for aggregating chunk signals into document classification.
    
    This service takes classification signals extracted from individual chunks
    during normalization and aggregates them using weighted averaging to
    determine the overall document type.
    
    Features:
    - Weighted signal aggregation
    - Chunk importance weighting (first page, declarations, keywords)
    - Confidence-based decision thresholds
    - Optional fallback classification for low-confidence cases
    
    Attributes:
        accept_threshold: Confidence threshold for auto-accepting classification
        review_threshold: Confidence threshold below which fallback is triggered
    """
    
    def __init__(
        self,
        accept_threshold: float = ACCEPT_THRESHOLD,
        review_threshold: float = REVIEW_THRESHOLD,
    ):
        """Initialize classification service.
        
        Args:
            accept_threshold: Confidence threshold for auto-accept (default: 0.75)
            review_threshold: Confidence threshold for fallback (default: 0.50)
        """
        self.accept_threshold = accept_threshold
        self.review_threshold = review_threshold
        
        LOGGER.info(
            "Initialized classification service",
            extra={
                "accept_threshold": accept_threshold,
                "review_threshold": review_threshold,
                "document_types": len(DOCUMENT_TYPES),
            }
        )
    
    def aggregate_signals(
        self,
        chunk_signals: List[Dict[str, Any]],
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Aggregate per-chunk signals into document-level classification.
        
        This method combines signals from all chunks using weighted averaging,
        applies chunk importance weighting, and determines the final classification
        with confidence score.
        
        Args:
            chunk_signals: List of signal dicts from each chunk, each containing:
                - signals: Dict[str, float] - per-class confidence scores
                - keywords: List[str] - extracted keywords
                - entities: Dict[str, Any] - extracted entities
                - confidence: float - chunk-level confidence
            chunk_metadata: Optional list of metadata dicts for each chunk:
                - page_number: int
                - section_name: Optional[str]
                - chunk_index: int
                
        Returns:
            dict: Classification result containing:
                - classified_type: str - predicted document type
                - confidence: float - confidence score (0.0-1.0)
                - all_scores: Dict[str, float] - scores for all document types
                - method: str - "aggregate" or "fallback"
                - chunks_used: int - number of chunks processed
                - fallback_used: bool
                - decision_details: Dict - additional metadata
                
        Example:
            >>> service = ClassificationService()
            >>> signals = [
            ...     {"signals": {"policy": 0.9, "claim": 0.1, ...}, "keywords": [...], ...},
            ...     {"signals": {"policy": 0.8, "claim": 0.2, ...}, "keywords": [...], ...},
            ... ]
            >>> result = service.aggregate_signals(signals)
            >>> print(result["classified_type"])  # "policy"
            >>> print(result["confidence"])  # 0.85
        """
        if not chunk_signals:
            LOGGER.warning("No chunk signals provided for aggregation")
            return self._create_empty_result()
        
        LOGGER.info(
            "Starting signal aggregation",
            extra={"chunks_count": len(chunk_signals)}
        )
        
        # Calculate chunk weights
        weights = self._calculate_chunk_weights(chunk_signals, chunk_metadata)
        
        # Aggregate signals across chunks
        aggregated_scores = self._aggregate_scores(chunk_signals, weights)
        
        # Normalize scores to 0-1 range
        normalized_scores = self._normalize_scores(aggregated_scores)
        
        # Select top class and confidence
        top_class, top_score = max(normalized_scores.items(), key=lambda x: x[1])
        
        # Collect all keywords and entities
        all_keywords = self._collect_keywords(chunk_signals)
        all_entities = self._collect_entities(chunk_signals)
        
        # Create result
        result = {
            "classified_type": top_class,
            "confidence": float(top_score),
            "all_scores": {k: float(v) for k, v in normalized_scores.items()},
            "method": "aggregate",
            "chunks_used": len(chunk_signals),
            "fallback_used": False,
            "decision_details": {
                "aggregated_scores": {k: float(v) for k, v in aggregated_scores.items()},
                "top_class": top_class,
                "top_score": float(top_score),
                "keywords": all_keywords[:20],  # Top 20 keywords
                "entities": all_entities,
                "weights_applied": len([w for w in weights if w != DEFAULT_CHUNK_WEIGHT]),
            }
        }
        
        LOGGER.info(
            "Signal aggregation completed",
            extra={
                "classified_type": top_class,
                "confidence": float(top_score),
                "chunks_used": len(chunk_signals),
                "needs_fallback": top_score < self.review_threshold,
            }
        )
        
        return result
    
    def _calculate_chunk_weights(
        self,
        chunk_signals: List[Dict[str, Any]],
        chunk_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> List[float]:
        """Calculate importance weights for each chunk.
        
        Weights are based on:
        - Page number (first page gets higher weight)
        - Keywords (declarations page, policy numbers, etc.)
        - Chunk confidence
        
        Args:
            chunk_signals: List of signal dicts
            chunk_metadata: Optional metadata for each chunk
            
        Returns:
            List of weights (one per chunk)
        """
        weights = []
        
        for i, signal in enumerate(chunk_signals):
            weight = DEFAULT_CHUNK_WEIGHT
            
            # Apply page-based weighting
            if chunk_metadata and i < len(chunk_metadata):
                metadata = chunk_metadata[i]
                page_number = metadata.get("page_number", 1)
                
                # First page gets higher weight
                if page_number == 1:
                    weight *= FIRST_PAGE_WEIGHT
            
            # Apply keyword-based weighting
            keywords = signal.get("keywords", [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Check for declarations page
                if "declarations" in keyword_lower and "page" in keyword_lower:
                    weight *= DECLARATIONS_PAGE_WEIGHT
                    break
                
                # Check for other important keywords
                for key_phrase, multiplier in KEYWORD_MULTIPLIERS.items():
                    if key_phrase in keyword_lower:
                        weight *= multiplier
                        break
            
            # Apply chunk confidence weighting
            chunk_confidence = signal.get("confidence", 1.0)
            if chunk_confidence > 0:
                weight *= chunk_confidence
            
            weights.append(weight)
        
        LOGGER.debug(
            "Calculated chunk weights",
            extra={
                "weights": weights,
                "max_weight": max(weights) if weights else 0,
                "min_weight": min(weights) if weights else 0,
            }
        )
        
        return weights
    
    def _aggregate_scores(
        self,
        chunk_signals: List[Dict[str, Any]],
        weights: List[float],
    ) -> Dict[str, float]:
        """Aggregate per-chunk signals using weighted averaging.
        
        Args:
            chunk_signals: List of signal dicts
            weights: Weight for each chunk
            
        Returns:
            Dict of aggregated scores for each document type
        """
        # Initialize totals
        totals = {doc_type: 0.0 for doc_type in DOCUMENT_TYPES}
        total_weight = 0.0
        
        # Aggregate weighted scores
        for signal, weight in zip(chunk_signals, weights):
            signals = signal.get("signals", {})
            
            for doc_type in DOCUMENT_TYPES:
                score = signals.get(doc_type, 0.0)
                totals[doc_type] += score * weight
            
            total_weight += weight
        
        # Average by total weight
        if total_weight > 0:
            for doc_type in totals:
                totals[doc_type] /= total_weight
        
        return totals
    
    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to 0-1 range.
        
        Args:
            scores: Raw aggregated scores
            
        Returns:
            Normalized scores (sum approximately 1.0)
        """
        max_score = max(scores.values()) if scores else 1.0
        
        if max_score == 0:
            # All scores are zero, return uniform distribution
            return {k: 1.0 / len(DOCUMENT_TYPES) for k in DOCUMENT_TYPES}
        
        # Normalize by max score
        normalized = {k: v / max_score for k, v in scores.items()}
        
        # Ensure minimum confidence
        for k in normalized:
            if normalized[k] < MIN_CONFIDENCE:
                normalized[k] = 0.0
        
        return normalized
    
    def _collect_keywords(self, chunk_signals: List[Dict[str, Any]]) -> List[str]:
        """Collect and deduplicate keywords from all chunks.
        
        Args:
            chunk_signals: List of signal dicts
            
        Returns:
            List of unique keywords
        """
        all_keywords = []
        seen = set()
        
        for signal in chunk_signals:
            keywords = signal.get("keywords", [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in seen:
                    all_keywords.append(keyword)
                    seen.add(keyword_lower)
        
        return all_keywords
    
    def _collect_entities(self, chunk_signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Collect and merge entities from all chunks.
        
        Args:
            chunk_signals: List of signal dicts
            
        Returns:
            Dict of merged entities
        """
        merged_entities = {}
        
        for signal in chunk_signals:
            entities = signal.get("entities", {})
            for key, value in entities.items():
                # Keep first occurrence of each entity type
                if key not in merged_entities and value:
                    merged_entities[key] = value
        
        return merged_entities
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """Create empty classification result for error cases."""
        return {
            "classified_type": "correspondence",  # Default fallback
            "confidence": 0.0,
            "all_scores": {doc_type: 0.0 for doc_type in DOCUMENT_TYPES},
            "method": "default",
            "chunks_used": 0,
            "fallback_used": False,
            "decision_details": {},
        }
    
    def needs_fallback(self, classification_result: Dict[str, Any]) -> bool:
        """Check if classification needs fallback/review.
        
        Args:
            classification_result: Result from aggregate_signals()
            
        Returns:
            bool: True if confidence is below review threshold
        """
        confidence = classification_result.get("confidence", 0.0)
        return confidence < self.review_threshold
    
    def is_acceptable(self, classification_result: Dict[str, Any]) -> bool:
        """Check if classification is acceptable without review.
        
        Args:
            classification_result: Result from aggregate_signals()
            
        Returns:
            bool: True if confidence is above accept threshold
        """
        confidence = classification_result.get("confidence", 0.0)
        return confidence >= self.accept_threshold
