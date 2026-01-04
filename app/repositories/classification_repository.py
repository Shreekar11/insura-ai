"""Repository for classification-related database operations.

This repository handles all data access operations related to document
classification, including signals and final document classifications.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChunkClassificationSignal, DocumentClassification
from app.repositories.base_repository import BaseRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ClassificationRepository(BaseRepository[ChunkClassificationSignal]):
    """Repository for managing classification signals and document classifications.
    
    This repository provides data access methods for classification operations,
    separating database logic from business logic.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize classification repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_classification_signal(
        self,
        chunk_id: UUID,
        signals: Dict[str, float],
        model_name: str,
        keywords: Optional[List[str]] = None,
        entities: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> ChunkClassificationSignal:
        """Create a classification signal record for a chunk.
        
        Args:
            chunk_id: ID of the document chunk
            signals: Dictionary mapping document types to confidence scores
            model_name: Name of the model used for classification
            keywords: List of extracted keywords
            entities: Dictionary of extracted entities
            confidence: Overall confidence score for this signal
            
        Returns:
            ChunkClassificationSignal: The created signal record
            
        Example:
            >>> repo = ClassificationRepository(session)
            >>> signal = await repo.create_classification_signal(
            ...     chunk_id=chunk_uuid,
            ...     signals={"policy": 0.9, "claim": 0.1},
            ...     model_name="mistral-large",
            ...     keywords=["premium", "coverage"],
            ...     confidence=0.9
            ... )
        """
        signal = ChunkClassificationSignal(
            chunk_id=chunk_id,
            signals=signals,
            model_name=model_name,
            keywords=keywords,
            entities=entities,
            model_confidence=confidence,
        )
        self.session.add(signal)
        await self.session.flush()
        
        LOGGER.debug(
            "Classification signal created",
            extra={
                "chunk_id": str(chunk_id),
                "model": model_name,
                "signals": signals,
                "confidence": confidence,
            }
        )
        
        return signal

    async def get_signals_by_document(
        self, 
        document_id: UUID
    ) -> List[ChunkClassificationSignal]:
        """Get all classification signals for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List[ChunkClassificationSignal]: List of signals ordered by chunk
            
        Example:
            >>> repo = ClassificationRepository(session)
            >>> signals = await repo.get_signals_by_document(doc_id)
            >>> for signal in signals:
            ...     print(signal.signals)
        """
        from app.database.models import DocumentChunk
        
        query = (
            select(ChunkClassificationSignal)
            .join(DocumentChunk, ChunkClassificationSignal.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(query)
        signals = list(result.scalars().all())
        
        LOGGER.debug(
            "Retrieved classification signals",
            extra={
                "document_id": str(document_id),
                "signal_count": len(signals),
            }
        )
        
        return signals

    async def get_signals_by_chunk(
        self, 
        chunk_id: UUID
    ) -> List[ChunkClassificationSignal]:
        """Get all classification signals for a specific chunk.
        
        Args:
            chunk_id: ID of the chunk
            
        Returns:
            List[ChunkClassificationSignal]: List of signals for the chunk
        """
        query = select(ChunkClassificationSignal).where(
            ChunkClassificationSignal.chunk_id == chunk_id
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_document_classification(
        self,
        document_id: UUID,
        classified_type: str,
        confidence: float,
        classifier_model: str,
        decision_details: Optional[Dict[str, Any]] = None,
    ) -> DocumentClassification:
        """Create a document classification record.
        
        This represents the final aggregated classification for a document.
        
        Args:
            document_id: ID of the document being classified
            classified_type: The classified document type (e.g., "policy", "claim")
            confidence: Confidence score (0.0-1.0)
            classifier_model: Name of the model/method used for classification
            decision_details: Additional metadata about the classification decision
            
        Returns:
            DocumentClassification: The created classification record
            
        Example:
            >>> repo = ClassificationRepository(session)
            >>> classification = await repo.create_document_classification(
            ...     document_id=doc_uuid,
            ...     classified_type="policy",
            ...     confidence=0.95,
            ...     classifier_model="aggregate",
            ...     decision_details={"method": "weighted_average", "signals_count": 10}
            ... )
        """
        classification = DocumentClassification(
            document_id=document_id,
            classified_type=classified_type,
            confidence=confidence,
            classifier_model=classifier_model,
            decision_details=decision_details,
        )
        self.session.add(classification)
        await self.session.flush()
        
        LOGGER.info(
            "Document classification created",
            extra={
                "document_id": str(document_id),
                "classified_type": classified_type,
                "confidence": confidence,
                "model": classifier_model,
            }
        )
        
        return classification

    async def get_document_classification(
        self, 
        document_id: UUID
    ) -> Optional[DocumentClassification]:
        """Get the classification for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Optional[DocumentClassification]: The classification if found, None otherwise
        """
        query = select(DocumentClassification).where(
            DocumentClassification.document_id == document_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_document_classification(
        self,
        document_id: UUID,
        classified_type: str,
        confidence: float,
        decision_details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update an existing document classification.
        
        Args:
            document_id: ID of the document
            classified_type: Updated classification type
            confidence: Updated confidence score
            decision_details: Updated decision details
            
        Returns:
            bool: True if updated successfully, False if classification not found
        """
        classification = await self.get_document_classification(document_id)
        if not classification:
            LOGGER.warning(
                "Document classification not found for update",
                extra={"document_id": str(document_id)}
            )
            return False
        
        classification.classified_type = classified_type
        classification.confidence = confidence
        if decision_details is not None:
            classification.decision_details = decision_details
        
        await self.session.flush()
        
        LOGGER.info(
            "Document classification updated",
            extra={
                "document_id": str(document_id),
                "classified_type": classified_type,
                "confidence": confidence,
            }
        )
        
        return True

    async def delete_document_classification(
        self, 
        document_id: UUID
    ) -> bool:
        """Delete a document classification.
        
        Args:
            document_id: ID of the document
            
        Returns:
            bool: True if deleted, False if not found
        """
        classification = await self.get_document_classification(document_id)
        if not classification:
            return False
        
        await self.session.delete(classification)
        await self.session.flush()
        
        LOGGER.info(
            "Document classification deleted",
            extra={"document_id": str(document_id)}
        )
        
        return True
