"""Batch processing utilities for OCR pipeline optimization.

This module provides shared utilities for batching chunks and processing
them efficiently through the unified extraction pipeline.
"""

from typing import List, Dict, Any, TypeVar, Optional
from uuid import UUID
import hashlib

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

T = TypeVar('T')


class BatchProcessor:
    """Utilities for batch processing in the OCR pipeline."""
    
    @staticmethod
    def create_batches(items: List[T], batch_size: int) -> List[List[T]]:
        """Create batches from a list of items.
        
        Args:
            items: List of items to batch
            batch_size: Number of items per batch
            
        Returns:
            List of batches, each containing up to batch_size items
            
        Example:
            >>> items = [1, 2, 3, 4, 5]
            >>> batches = BatchProcessor.create_batches(items, 2)
            >>> batches
            [[1, 2], [3, 4], [5]]
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        
        batches = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batches.append(batch)
        
        LOGGER.debug(
            f"Created {len(batches)} batches from {len(items)} items "
            f"(batch_size={batch_size})"
        )
        
        return batches
    
    @staticmethod
    def merge_batch_results(
        batch_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Merge results from multiple batches.
        
        Args:
            batch_results: List of batch result dictionaries
            
        Returns:
            Merged dictionary containing all results
            
        Example:
            >>> batch1 = {"ch_001": {...}, "ch_002": {...}}
            >>> batch2 = {"ch_003": {...}}
            >>> merged = BatchProcessor.merge_batch_results([batch1, batch2])
            >>> len(merged)
            3
        """
        merged = {}
        
        for batch_result in batch_results:
            if isinstance(batch_result, dict):
                merged.update(batch_result)
        
        LOGGER.debug(
            f"Merged {len(batch_results)} batch results into "
            f"{len(merged)} total results"
        )
        
        return merged
    
    @staticmethod
    def validate_batch_response(
        response: Dict[str, Any],
        expected_chunk_ids: List[str]
    ) -> tuple[bool, List[str]]:
        """Validate that batch response contains all expected chunks.
        
        Args:
            response: Batch response dictionary
            expected_chunk_ids: List of expected chunk IDs
            
        Returns:
            Tuple of (is_valid, missing_chunk_ids)
            
        Example:
            >>> response = {"ch_001": {...}, "ch_002": {...}}
            >>> expected = ["ch_001", "ch_002", "ch_003"]
            >>> is_valid, missing = BatchProcessor.validate_batch_response(
            ...     response, expected
            ... )
            >>> is_valid
            False
            >>> missing
            ['ch_003']
        """
        if not isinstance(response, dict):
            LOGGER.error("Batch response is not a dictionary")
            return False, expected_chunk_ids
        
        missing_chunks = []
        for chunk_id in expected_chunk_ids:
            if chunk_id not in response:
                missing_chunks.append(chunk_id)
        
        is_valid = len(missing_chunks) == 0
        
        if not is_valid:
            LOGGER.warning(
                f"Batch response missing {len(missing_chunks)} chunks: "
                f"{missing_chunks}"
            )
        
        return is_valid, missing_chunks
    
    @staticmethod
    def handle_partial_batch_failure(
        batch: List[Any],
        failed_chunk_ids: List[str],
        fallback_handler: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Handle partial batch failures with fallback processing.
        
        Args:
            batch: Original batch items
            failed_chunk_ids: List of chunk IDs that failed
            fallback_handler: Optional function to handle failed chunks
            
        Returns:
            Dictionary of fallback results for failed chunks
            
        Example:
            >>> def fallback(chunk):
            ...     return {"error": "fallback"}
            >>> batch = [{"id": "ch_001"}, {"id": "ch_002"}]
            >>> failed = ["ch_002"]
            >>> results = BatchProcessor.handle_partial_batch_failure(
            ...     batch, failed, fallback
            ... )
        """
        fallback_results = {}
        
        if not fallback_handler:
            LOGGER.warning(
                f"No fallback handler provided for {len(failed_chunk_ids)} "
                "failed chunks"
            )
            return fallback_results
        
        for chunk_id in failed_chunk_ids:
            try:
                # Find the chunk in the batch
                chunk = next(
                    (item for item in batch if item.get("chunk_id") == chunk_id),
                    None
                )
                
                if chunk:
                    fallback_result = fallback_handler(chunk)
                    fallback_results[chunk_id] = fallback_result
                    LOGGER.info(f"Fallback processing succeeded for {chunk_id}")
                else:
                    LOGGER.error(f"Chunk {chunk_id} not found in batch")
                    
            except Exception as e:
                LOGGER.error(
                    f"Fallback processing failed for {chunk_id}: {e}",
                    exc_info=True
                )
        
        return fallback_results
    
    @staticmethod
    def generate_batch_id(chunk_ids: List[str]) -> str:
        """Generate a deterministic batch ID from chunk IDs.
        
        Args:
            chunk_ids: List of chunk IDs in the batch
            
        Returns:
            Deterministic batch ID (SHA256 hash)
            
        Example:
            >>> chunk_ids = ["ch_001", "ch_002", "ch_003"]
            >>> batch_id = BatchProcessor.generate_batch_id(chunk_ids)
            >>> len(batch_id)
            64
        """
        # Sort for determinism
        sorted_ids = sorted(chunk_ids)
        combined = "_".join(sorted_ids)
        
        # Generate SHA256 hash
        hash_obj = hashlib.sha256(combined.encode())
        batch_id = hash_obj.hexdigest()
        
        return batch_id
