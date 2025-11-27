"""Quality gate service for RAG ingestion.

This service enforces minimum quality thresholds before allowing documents
to be ingested into vector/graph stores, ensuring data quality.
"""

from typing import Dict, Any, List
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CanonicalEntity, EntityRelationship, ChunkEntityLink
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class QualityThresholds:
    """Minimum quality thresholds for RAG ingestion."""
    min_policy_numbers: int = 1
    min_insured_names: int = 1
    min_relationships: int = 1
    min_canonical_entities: int = 3


@dataclass
class QualityCheckResult:
    """Result of quality gate check."""
    passed: bool
    failures: List[str]
    report: Dict[str, Any]


class QualityGateService:
    """Enforces quality thresholds before RAG ingestion.
    
    This service checks that documents meet minimum quality requirements
    before being ingested into vector/graph stores. Documents that fail
    are logged for manual review.
    
    Attributes:
        session: Database session
        thresholds: Quality thresholds to enforce
    """
    
    def __init__(
        self,
        session: AsyncSession,
        thresholds: QualityThresholds = None
    ):
        """Initialize quality gate service.
        
        Args:
            session: Database session
            thresholds: Optional custom thresholds (uses defaults if None)
        """
        self.session = session
        self.thresholds = thresholds or QualityThresholds()
        
        LOGGER.info(
            "Initialized QualityGateService",
            extra={
                "thresholds": {
                    "min_policy_numbers": self.thresholds.min_policy_numbers,
                    "min_insured_names": self.thresholds.min_insured_names,
                    "min_relationships": self.thresholds.min_relationships,
                    "min_canonical_entities": self.thresholds.min_canonical_entities
                }
            }
        )
    
    async def check_document_quality(
        self,
        document_id: UUID
    ) -> QualityCheckResult:
        """Check if document meets quality thresholds.
        
        Args:
            document_id: Document ID to check
            
        Returns:
            QualityCheckResult with pass/fail status and details
        """
        LOGGER.info(
            "Starting quality gate check",
            extra={"document_id": str(document_id)}
        )
        
        # Gather quality metrics
        metrics = await self._gather_quality_metrics(document_id)
        
        # Check thresholds
        failures = []
        
        if metrics["policy_number_count"] < self.thresholds.min_policy_numbers:
            failures.append(
                f"Insufficient policy numbers: {metrics['policy_number_count']} < {self.thresholds.min_policy_numbers}"
            )
        
        if metrics["insured_name_count"] < self.thresholds.min_insured_names:
            failures.append(
                f"Insufficient insured names: {metrics['insured_name_count']} < {self.thresholds.min_insured_names}"
            )
        
        if metrics["relationship_count"] < self.thresholds.min_relationships:
            failures.append(
                f"Insufficient relationships: {metrics['relationship_count']} < {self.thresholds.min_relationships}"
            )
        
        if metrics["canonical_entity_count"] < self.thresholds.min_canonical_entities:
            failures.append(
                f"Insufficient canonical entities: {metrics['canonical_entity_count']} < {self.thresholds.min_canonical_entities}"
            )
        
        passed = len(failures) == 0
        
        result = QualityCheckResult(
            passed=passed,
            failures=failures,
            report=metrics
        )
        
        if passed:
            LOGGER.info(
                "Quality gate check PASSED",
                extra={
                    "document_id": str(document_id),
                    "metrics": metrics
                }
            )
        else:
            LOGGER.warning(
                "Quality gate check FAILED",
                extra={
                    "document_id": str(document_id),
                    "failures": failures,
                    "metrics": metrics
                }
            )
        
        return result
    
    async def _gather_quality_metrics(
        self,
        document_id: UUID
    ) -> Dict[str, Any]:
        """Gather quality metrics for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with quality metrics
        """
        # Get canonical entities for this document
        canonical_entities = await self._get_canonical_entities(document_id)
        
        # Count by type
        policy_numbers = [e for e in canonical_entities if e.entity_type == "POLICY_NUMBER"]
        insured_names = [e for e in canonical_entities if e.entity_type == "INSURED_NAME"]
        
        # Get relationships
        relationships = await self._get_relationships(document_id)
        
        metrics = {
            "canonical_entity_count": len(canonical_entities),
            "policy_number_count": len(policy_numbers),
            "insured_name_count": len(insured_names),
            "relationship_count": len(relationships),
            "entity_types": list(set(e.entity_type for e in canonical_entities)),
            "relationship_types": list(set(r.relationship_type for r in relationships))
        }
        
        LOGGER.debug(
            "Gathered quality metrics",
            extra={
                "document_id": str(document_id),
                "metrics": metrics
            }
        )
        
        return metrics
    
    async def _get_canonical_entities(
        self,
        document_id: UUID
    ) -> List[CanonicalEntity]:
        """Get canonical entities for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of canonical entities
        """
        from app.database.models import NormalizedChunk, DocumentChunk
        
        # Get all chunk IDs for this document
        stmt = select(NormalizedChunk.id).join(
            NormalizedChunk.chunk
        ).where(
            DocumentChunk.document_id == document_id
        )
        result = await self.session.execute(stmt)
        chunk_ids = [row[0] for row in result.all()]
        
        if not chunk_ids:
            return []
        
        # Get canonical entities linked to these chunks
        stmt = select(CanonicalEntity).join(
            ChunkEntityLink,
            ChunkEntityLink.canonical_entity_id == CanonicalEntity.id
        ).where(
            ChunkEntityLink.chunk_id.in_(chunk_ids)
        ).distinct()
        
        result = await self.session.execute(stmt)
        entities = result.scalars().all()
        
        return list(entities)
    
    async def _get_relationships(
        self,
        document_id: UUID
    ) -> List[EntityRelationship]:
        """Get relationships for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of relationships
        """
        # Get canonical entities for this document
        canonical_entities = await self._get_canonical_entities(document_id)
        
        if not canonical_entities:
            return []
        
        entity_ids = [e.id for e in canonical_entities]
        
        # Get relationships where both source and target are in this document's entities
        stmt = select(EntityRelationship).where(
            EntityRelationship.source_entity_id.in_(entity_ids),
            EntityRelationship.target_entity_id.in_(entity_ids)
        )
        
        result = await self.session.execute(stmt)
        relationships = result.scalars().all()
        
        return list(relationships)
    
    def get_quality_report(
        self,
        check_result: QualityCheckResult
    ) -> str:
        """Generate human-readable quality report.
        
        Args:
            check_result: Quality check result
            
        Returns:
            Formatted report string
        """
        report_lines = [
            "=" * 60,
            "QUALITY GATE REPORT",
            "=" * 60,
            f"Status: {'PASSED' if check_result.passed else 'FAILED'}",
            ""
        ]
        
        if check_result.failures:
            report_lines.append("Failures:")
            for failure in check_result.failures:
                report_lines.append(f"  - {failure}")
            report_lines.append("")
        
        report_lines.extend([
            "Metrics:",
            f"  Canonical Entities: {check_result.report['canonical_entity_count']}",
            f"  Policy Numbers: {check_result.report['policy_number_count']}",
            f"  Insured Names: {check_result.report['insured_name_count']}",
            f"  Relationships: {check_result.report['relationship_count']}",
            "",
            f"  Entity Types: {', '.join(check_result.report['entity_types'])}",
            f"  Relationship Types: {', '.join(check_result.report['relationship_types'])}",
            "=" * 60
        ])
        
        return "\n".join(report_lines)
