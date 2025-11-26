"""Unified batch extractor for optimized OCR pipeline.

This service combines normalization, entity extraction, and section detection
into a single LLM call per batch of chunks, reducing API calls by 75-85%.

Architecture:
- Processes 3 chunks per batch (configurable)
- Single unified prompt returns normalized text, entities, section types, and signals
- Batch-aware response parsing with fallback handling
- Maintains data quality through few-shot prompting
"""

import json
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_service import BaseService
from app.core.unified_llm import UnifiedLLMClient
from app.services.extraction.batch_processor import BatchProcessor
from app.prompts import UNIFIED_BATCH_EXTRACTION_PROMPT
from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


class UnifiedBatchExtractor(BaseService):
    """Unified extractor that processes multiple chunks in a single LLM call.
    
    This service combines three previously separate operations:
    1. Text normalization (OCR cleanup)
    2. Entity extraction (insurance entities)
    3. Section type detection (coverages, conditions, exclusions, etc.)
    
    By batching chunks and combining operations, we reduce LLM calls from
    2-3 per chunk to 1 per batch of 3 chunks (6x reduction).
    
    Attributes:
        session: SQLAlchemy async session
        client: GeminiClient for LLM API calls
        batch_size: Number of chunks to process per batch
        timeout: Timeout for LLM API calls in seconds
    """
    
    # Unified extraction prompt is imported from app.prompts
    # See app/prompts/system_prompts.py for the full prompt definition
    
    def __init__(
        self,
        session: AsyncSession,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "google/gemini-2.0-flash-001",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        batch_size: int = 3,
        timeout: int = 90,
        max_retries: int = 3,
    ):
        """Initialize unified batch extractor.
        
        Args:
            session: SQLAlchemy async session
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model to use
            openrouter_api_url: OpenRouter API URL
            batch_size: Number of chunks per batch
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        super().__init__(repository=None)
        self.session = session
        self.provider = provider
        self.batch_size = batch_size
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Determine which API key and model to use
        if provider == "openrouter":
            if not openrouter_api_key:
                raise ValueError("openrouter_api_key required when provider='openrouter'")
            api_key = openrouter_api_key
            model = openrouter_model
            base_url = openrouter_api_url
        else:  # gemini
            if not gemini_api_key:
                raise ValueError("gemini_api_key required when provider='gemini'")
            api_key = gemini_api_key
            model = gemini_model
            base_url = None
        
        # Store model for external access
        self.model = model
        
        # Initialize UnifiedLLMClient
        self.client = UnifiedLLMClient(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            fallback_to_gemini=False,
        )
        
        LOGGER.info(
            f"Initialized UnifiedBatchExtractor with batch_size={batch_size}, "
            f"provider={provider}, model={model}"
        )
    
    async def extract_batch(
        self,
        chunks: List[Dict[str, Any]],
        document_id: UUID
    ) -> Dict[str, Dict[str, Any]]:
        """Extract normalized text, entities, and section types from a batch of chunks.
        
        This is the main entry point for batch processing. It takes a list of
        chunks and returns unified extraction results for all chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'chunk_id' and 'text' keys
            document_id: Document UUID for logging/tracking
            
        Returns:
            Dictionary mapping chunk_id to extraction results:
            {
                "ch_001": {
                    "normalized_text": "...",
                    "entities": [...],
                    "section_type": "coverages",
                    "classification_signals": {...}
                },
                ...
            }
            
        Raises:
            APIClientError: If LLM API call fails after retries
            ValueError: If chunks list is empty or invalid
            
        Example:
            >>> chunks = [
            ...     {"chunk_id": "ch_001", "text": "Policy Number: ABC123..."},
            ...     {"chunk_id": "ch_002", "text": "Coverage: Property..."}
            ... ]
            >>> results = await extractor.extract_batch(chunks, document_id)
            >>> results["ch_001"]["normalized_text"]
            'Policy Number: ABC123...'
        """
        if not chunks:
            raise ValueError("Chunks list cannot be empty")
        
        chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        
        LOGGER.info(
            f"Starting unified batch extraction for {len(chunks)} chunks",
            extra={
                "document_id": str(document_id),
                "chunk_ids": chunk_ids,
                "batch_size": len(chunks)
            }
        )
        
        try:
            # Call LLM API with batch
            results = await self._call_llm_api(chunks)
            
            # Validate response
            is_valid, missing_chunks = BatchProcessor.validate_batch_response(
                results, chunk_ids
            )
            
            if not is_valid:
                LOGGER.warning(
                    f"Batch response missing {len(missing_chunks)} chunks, "
                    "attempting fallback processing",
                    extra={"missing_chunks": missing_chunks}
                )
                
                # Handle partial failures with fallback
                fallback_results = await self._handle_missing_chunks(
                    chunks, missing_chunks, document_id
                )
                results.update(fallback_results)
            
            LOGGER.info(
                f"Unified batch extraction completed for {len(results)} chunks",
                extra={
                    "document_id": str(document_id),
                    "success_count": len(results)
                }
            )
            
            return results
            
        except Exception as e:
            LOGGER.error(
                f"Unified batch extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id), "chunk_count": len(chunks)}
            )
            raise
    
    async def run(
        self,
        chunks: List[Dict[str, Any]],
        document_id: UUID
    ) -> Dict[str, Dict[str, Any]]:
        """Execute batch extraction (BaseService compatibility).
        
        This method provides compatibility with BaseService.execute() pattern.
        
        Args:
            chunks: List of chunk dictionaries
            document_id: Document UUID
            
        Returns:
            Extraction results dictionary
        """
        return await self.extract_batch(chunks, document_id)
    
    async def _call_llm_api(
        self,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Call LLM API for batch extraction.
        
        Args:
            chunks: List of chunk dictionaries
            
        Returns:
            Parsed extraction results
            
        Raises:
            APIClientError: If API call fails
        """
        # Prepare batch input
        batch_input = {
            "chunks": chunks
        }
        
        input_json = json.dumps(batch_input, indent=2)
        
        LOGGER.debug(
            f"Calling LLM API with {len(chunks)} chunks",
            extra={"chunk_count": len(chunks)}
        )
        
        try:
            # Call Gemini API
            prompt_text = f"Process these chunks:\n\n{input_json}"
            response = await self.client.generate_content(
                contents=prompt_text,
                system_instruction=UNIFIED_BATCH_EXTRACTION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            parsed = self._parse_response(response)
            
            return parsed.get("results", {})
            
        except Exception as e:
            LOGGER.error(f"LLM API call failed: {e}", exc_info=True)
            raise APIClientError(f"Unified batch extraction API call failed: {e}")
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate LLM response.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            Parsed response dictionary
        """
        parsed = parse_json_safely(response_text)
        
        if parsed is None:
            LOGGER.error(
                "Failed to parse LLM response as JSON",
                extra={"response_preview": response_text[:500]}
            )
            return {"results": {}}
        
        if not isinstance(parsed, dict):
            LOGGER.warning("LLM response is not a dictionary")
            return {"results": {}}
        
        return parsed
    
    async def _handle_missing_chunks(
        self,
        original_chunks: List[Dict[str, Any]],
        missing_chunk_ids: List[str],
        document_id: UUID
    ) -> Dict[str, Dict[str, Any]]:
        """Handle chunks that were missing from batch response.
        
        Attempts to process missing chunks individually as fallback.
        
        Args:
            original_chunks: Original chunk list
            missing_chunk_ids: List of chunk IDs that failed
            document_id: Document UUID
            
        Returns:
            Dictionary of fallback results
        """
        fallback_results = {}
        
        for chunk_id in missing_chunk_ids:
            # Find the chunk
            chunk = next(
                (c for c in original_chunks if c["chunk_id"] == chunk_id),
                None
            )
            
            if not chunk:
                LOGGER.error(f"Chunk {chunk_id} not found in original batch")
                continue
            
            try:
                # Process single chunk as fallback
                LOGGER.info(f"Attempting fallback processing for {chunk_id}")
                
                single_result = await self._call_llm_api([chunk])
                
                if chunk_id in single_result:
                    fallback_results[chunk_id] = single_result[chunk_id]
                    LOGGER.info(f"Fallback processing succeeded for {chunk_id}")
                else:
                    LOGGER.error(f"Fallback processing failed for {chunk_id}")
                    
            except Exception as e:
                LOGGER.error(
                    f"Fallback processing error for {chunk_id}: {e}",
                    exc_info=True
                )
        
        return fallback_results
