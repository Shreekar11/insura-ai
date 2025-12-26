"""Repository for managing table extraction data.

This repository handles persistence of:
- TableJSON as DocumentTable (first-class table storage)
- SOV items extracted from tables
- Loss Run claims extracted from tables
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.base_repository import BaseRepository
from app.database.models import SOVItem, LossRunClaim, DocumentTable
from app.models.table_json import TableJSON, TableExtractionSource, create_table_id
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class TableRepository:
    """Repository for table extraction data.
    
    Handles persistence of:
    - DocumentTable: First-class table storage with full TableJSON structure
    - SOVItem: Statement of Values items extracted from tables
    - LossRunClaim: Loss run claims extracted from tables
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize table repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self.sov_repo = BaseRepository(session, SOVItem)
        self.loss_run_repo = BaseRepository(session, LossRunClaim)
    
    async def save_sov_items(
        self,
        document_id: UUID,
        sov_items: List[SOVItem]
    ) -> int:
        """Save SOV items to database.
        
        Args:
            document_id: Document ID
            sov_items: List of SOVItem objects
            
        Returns:
            Number of items saved
        """
        saved_count = 0
        
        for item in sov_items:
            # Ensure document_id is set
            if not item.document_id:
                item.document_id = document_id
            
            try:
                # Add item to session (don't use repo.create as it may have issues with existing objects)
                self.session.add(item)
                saved_count += 1
            except Exception as e:
                LOGGER.warning(
                    f"Failed to save SOV item: {e}",
                    extra={
                        "document_id": str(document_id),
                        "location_number": item.location_number
                    }
                )
        
        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            LOGGER.error(
                f"Failed to commit SOV items: {e}",
                extra={"document_id": str(document_id)}
            )
            raise
        
        LOGGER.info(
            f"Saved {saved_count}/{len(sov_items)} SOV items",
            extra={
                "document_id": str(document_id),
                "saved": saved_count,
                "total": len(sov_items)
            }
        )
        
        return saved_count
    
    async def save_loss_run_claims(
        self,
        document_id: UUID,
        claims: List[LossRunClaim]
    ) -> int:
        """Save Loss Run claims to database.
        
        Args:
            document_id: Document ID
            claims: List of LossRunClaim objects
            
        Returns:
            Number of claims saved
        """
        saved_count = 0
        
        for claim in claims:
            # Ensure document_id is set
            if not claim.document_id:
                claim.document_id = document_id
            
            try:
                # Add claim to session (don't use repo.create as it may have issues with existing objects)
                self.session.add(claim)
                saved_count += 1
            except Exception as e:
                LOGGER.warning(
                    f"Failed to save Loss Run claim: {e}",
                    extra={
                        "document_id": str(document_id),
                        "claim_number": claim.claim_number
                    }
                )
        
        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            LOGGER.error(
                f"Failed to commit Loss Run claims: {e}",
                extra={"document_id": str(document_id)}
            )
            raise
        
        LOGGER.info(
            f"Saved {saved_count}/{len(claims)} Loss Run claims",
            extra={
                "document_id": str(document_id),
                "saved": saved_count,
                "total": len(claims)
            }
        )
        
        return saved_count
    
    async def get_sov_items(self, document_id: UUID) -> List[SOVItem]:
        """Get all SOV items for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of SOVItem objects
        """
        stmt = select(SOVItem).where(SOVItem.document_id == document_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_loss_run_claims(self, document_id: UUID) -> List[LossRunClaim]:
        """Get all Loss Run claims for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of LossRunClaim objects
        """
        stmt = select(LossRunClaim).where(LossRunClaim.document_id == document_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    # =========================================================================
    # DocumentTable (TableJSON) Methods
    # =========================================================================
    
    async def save_table_json(
        self,
        document_id: UUID,
        table_json: TableJSON
    ) -> DocumentTable:
        """Save a TableJSON as a DocumentTable.
        
        Args:
            document_id: Document ID
            table_json: TableJSON object to persist
            
        Returns:
            Created DocumentTable object
        """
        # Create stable table ID
        stable_id = create_table_id(
            document_id, 
            table_json.page_number, 
            table_json.table_index
        )
        
        # Check if table already exists
        existing = await self.get_document_table_by_stable_id(stable_id)
        if existing:
            # Update existing table
            return await self._update_document_table(existing, table_json)
        
        # Create new DocumentTable
        doc_table = DocumentTable(
            document_id=document_id,
            page_number=table_json.page_number,
            table_index=table_json.table_index,
            stable_table_id=stable_id,
            table_json=table_json.to_dict(),
            table_bbox=table_json.table_bbox,
            num_rows=table_json.num_rows,
            num_cols=table_json.num_cols,
            header_rows=table_json.header_rows,
            canonical_headers=table_json.canonical_headers,
            table_type=table_json.classification.value if table_json.classification else None,
            classification_confidence=Decimal(str(table_json.classification_confidence)) if table_json.classification_confidence else None,
            extraction_source=table_json.source.value if isinstance(table_json.source, TableExtractionSource) else str(table_json.source),
            extractor_version=table_json.extractor_version,
            confidence_overall=Decimal(str(table_json.confidence_metrics.overall)) if table_json.confidence_metrics else None,
            confidence_metrics=table_json.confidence_metrics.to_dict() if table_json.confidence_metrics else None,
            raw_markdown=table_json.raw_markdown,
            notes=table_json.notes,
            additional_metadata=table_json.metadata
        )
        
        self.session.add(doc_table)
        
        try:
            await self.session.commit()
            await self.session.refresh(doc_table)
            
            LOGGER.info(
                f"Saved DocumentTable {stable_id}",
                extra={
                    "document_id": str(document_id),
                    "stable_table_id": stable_id,
                    "page_number": table_json.page_number,
                    "num_rows": table_json.num_rows,
                    "num_cols": table_json.num_cols,
                    "source": table_json.source.value if isinstance(table_json.source, TableExtractionSource) else str(table_json.source)
                }
            )
            
            return doc_table
            
        except Exception as e:
            await self.session.rollback()
            LOGGER.error(
                f"Failed to save DocumentTable: {e}",
                extra={
                    "document_id": str(document_id),
                    "stable_table_id": stable_id
                }
            )
            raise
    
    async def _update_document_table(
        self,
        existing: DocumentTable,
        table_json: TableJSON
    ) -> DocumentTable:
        """Update an existing DocumentTable with new TableJSON data.
        
        Args:
            existing: Existing DocumentTable
            table_json: New TableJSON data
            
        Returns:
            Updated DocumentTable
        """
        existing.table_json = table_json.to_dict()
        existing.table_bbox = table_json.table_bbox
        existing.num_rows = table_json.num_rows
        existing.num_cols = table_json.num_cols
        existing.header_rows = table_json.header_rows
        existing.canonical_headers = table_json.canonical_headers
        existing.table_type = table_json.classification.value if table_json.classification else None
        existing.classification_confidence = Decimal(str(table_json.classification_confidence)) if table_json.classification_confidence else None
        existing.extraction_source = table_json.source.value if isinstance(table_json.source, TableExtractionSource) else str(table_json.source)
        existing.extractor_version = table_json.extractor_version
        existing.confidence_overall = Decimal(str(table_json.confidence_metrics.overall)) if table_json.confidence_metrics else None
        existing.confidence_metrics = table_json.confidence_metrics.to_dict() if table_json.confidence_metrics else None
        existing.raw_markdown = table_json.raw_markdown
        existing.notes = table_json.notes
        existing.additional_metadata = table_json.metadata
        
        try:
            await self.session.commit()
            await self.session.refresh(existing)
            
            LOGGER.info(
                f"Updated DocumentTable {existing.stable_table_id}",
                extra={
                    "document_id": str(existing.document_id),
                    "stable_table_id": existing.stable_table_id
                }
            )
            
            return existing
            
        except Exception as e:
            await self.session.rollback()
            LOGGER.error(
                f"Failed to update DocumentTable: {e}",
                extra={"stable_table_id": existing.stable_table_id}
            )
            raise
    
    async def save_tables_json(
        self,
        document_id: UUID,
        tables: List[TableJSON]
    ) -> int:
        """Save multiple TableJSON objects as DocumentTables.
        
        Args:
            document_id: Document ID
            tables: List of TableJSON objects
            
        Returns:
            Number of tables saved
        """
        saved_count = 0
        
        for table_json in tables:
            try:
                await self.save_table_json(document_id, table_json)
                saved_count += 1
            except Exception as e:
                LOGGER.warning(
                    f"Failed to save table {table_json.table_id}: {e}",
                    extra={
                        "document_id": str(document_id),
                        "table_id": table_json.table_id
                    }
                )
        
        LOGGER.info(
            f"Saved {saved_count}/{len(tables)} DocumentTables",
            extra={
                "document_id": str(document_id),
                "saved": saved_count,
                "total": len(tables)
            }
        )
        
        return saved_count
    
    async def get_document_table_by_stable_id(
        self,
        stable_table_id: str
    ) -> Optional[DocumentTable]:
        """Get a DocumentTable by its stable ID.
        
        Args:
            stable_table_id: Stable table ID
            
        Returns:
            DocumentTable or None
        """
        stmt = select(DocumentTable).where(
            DocumentTable.stable_table_id == stable_table_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_document_tables(
        self,
        document_id: UUID,
        page_number: Optional[int] = None,
        table_type: Optional[str] = None
    ) -> List[DocumentTable]:
        """Get DocumentTables for a document with optional filtering.
        
        Args:
            document_id: Document ID
            page_number: Optional page number filter
            table_type: Optional table type filter
            
        Returns:
            List of DocumentTable objects
        """
        stmt = select(DocumentTable).where(
            DocumentTable.document_id == document_id
        )
        
        if page_number is not None:
            stmt = stmt.where(DocumentTable.page_number == page_number)
        
        if table_type is not None:
            stmt = stmt.where(DocumentTable.table_type == table_type)
        
        stmt = stmt.order_by(
            DocumentTable.page_number, 
            DocumentTable.table_index
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_tables_as_json(
        self,
        document_id: UUID,
        page_number: Optional[int] = None,
        table_type: Optional[str] = None
    ) -> List[TableJSON]:
        """Get tables as TableJSON objects.
        
        Args:
            document_id: Document ID
            page_number: Optional page number filter
            table_type: Optional table type filter
            
        Returns:
            List of TableJSON objects
        """
        doc_tables = await self.get_document_tables(
            document_id, 
            page_number, 
            table_type
        )
        
        tables = []
        for doc_table in doc_tables:
            try:
                table_json = TableJSON.from_dict(doc_table.table_json)
                
                # Force header reconstruction if headers are messy (from old extractions)
                # This ensures headers are cleaned even when loading from database
                if table_json._headers_need_reconstruction():
                    table_json.reconstruct_headers()
                    LOGGER.debug(
                        f"Reconstructed headers for table {doc_table.stable_table_id}",
                        extra={
                            "stable_table_id": doc_table.stable_table_id,
                            "old_headers": doc_table.canonical_headers[:3] if doc_table.canonical_headers else [],
                            "new_headers": table_json.canonical_headers[:3] if table_json.canonical_headers else []
                        }
                    )
                
                tables.append(table_json)
            except Exception as e:
                LOGGER.warning(
                    f"Failed to parse TableJSON from DocumentTable: {e}",
                    extra={
                        "document_id": str(document_id),
                        "stable_table_id": doc_table.stable_table_id
                    }
                )
        
        return tables
    
    async def delete_document_tables(
        self,
        document_id: UUID
    ) -> int:
        """Delete all DocumentTables for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Number of tables deleted
        """
        stmt = delete(DocumentTable).where(
            DocumentTable.document_id == document_id
        )
        
        result = await self.session.execute(stmt)
        await self.session.commit()
        
        deleted_count = result.rowcount
        
        LOGGER.info(
            f"Deleted {deleted_count} DocumentTables",
            extra={
                "document_id": str(document_id),
                "deleted": deleted_count
            }
        )
        
        return deleted_count
    
    async def update_table_classification(
        self,
        stable_table_id: str,
        table_type: str,
        confidence: float,
        reasoning: Optional[str] = None
    ) -> Optional[DocumentTable]:
        """Update the classification of a DocumentTable.
        
        Args:
            stable_table_id: Stable table ID
            table_type: Classification type
            confidence: Classification confidence
            reasoning: Optional reasoning text
            
        Returns:
            Updated DocumentTable or None if not found
        """
        doc_table = await self.get_document_table_by_stable_id(stable_table_id)
        if not doc_table:
            return None
        
        doc_table.table_type = table_type
        doc_table.classification_confidence = Decimal(str(confidence))
        doc_table.classification_reasoning = reasoning
        
        try:
            await self.session.commit()
            await self.session.refresh(doc_table)
            
            LOGGER.info(
                f"Updated classification for {stable_table_id}",
                extra={
                    "stable_table_id": stable_table_id,
                    "table_type": table_type,
                    "confidence": confidence
                }
            )
            
            return doc_table
            
        except Exception as e:
            await self.session.rollback()
            LOGGER.error(
                f"Failed to update classification: {e}",
                extra={"stable_table_id": stable_table_id}
            )
            raise

