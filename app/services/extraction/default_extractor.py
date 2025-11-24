"""Default extractor for unknown section types.

This extractor serves as a fallback when no specific extractor is registered
for a section type. It logs the unknown type and returns an empty list.
"""

from typing import List, Any, Optional
from uuid import UUID

from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class DefaultExtractor(BaseExtractor):
    """Default extractor for unknown section types.
    
    This extractor:
    - Logs unknown section types for monitoring
    - Returns empty list (no extraction)
    - Allows pipeline to continue gracefully
    - Helps identify new extraction types to implement
    """
    
    def get_extraction_prompt(self) -> str:
        """Get extraction prompt (not used for default extractor).
        
        Returns:
            str: Empty string
        """
        return ""
    
    async def extract(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """No extraction performed for unknown types.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            Empty list
        """
        LOGGER.info(
            "DefaultExtractor called - no specific extractor available",
            extra={
                "document_id": str(document_id),
                "chunk_id": str(chunk_id) if chunk_id else None,
                "text_length": len(text)
            }
        )
        
        return []
