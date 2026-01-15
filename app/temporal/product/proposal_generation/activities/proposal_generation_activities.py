"""Temporal activities for Proposal Generation workflow."""

from uuid import UUID
from typing import Dict, Any, List
from temporalio import activity

from app.core.database import async_session_maker
from app.services.product.proposal_generation.proposal_comparison_service import ProposalComparisonService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@activity.defn
async def detect_document_roles_activity(
    workflow_id: str,
    document_ids: List[str],
) -> Dict[str, str]:
    """Detect which document is expiring vs. renewal.
    
    Args:
        workflow_id: Workflow ID
        document_ids: List of document IDs
        
    Returns:
        Dict with 'expiring' and 'renewal' document IDs
    """
    async with async_session_maker() as session:
        service = ProposalComparisonService(session)
        
        uuid_doc_ids = [UUID(d) if isinstance(d, str) else d for d in document_ids]
        uuid_workflow_id = UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
        
        roles = await service.detect_document_roles(
            workflow_id=uuid_workflow_id,
            document_ids=uuid_doc_ids,
        )
        
        return {
            "expiring": str(roles["expiring"]),
            "renewal": str(roles["renewal"]),
        }


@activity.defn
async def compare_documents_for_proposal_activity(
    workflow_id: str,
    expiring_doc_id: str,
    renewal_doc_id: str,
) -> List[Dict[str, Any]]:
    """Compare two documents for proposal generation.
    
    Args:
        workflow_id: Workflow ID
        expiring_doc_id: Expiring document ID
        renewal_doc_id: Renewal document ID
        
    Returns:
        List of comparison changes as dicts
    """
    async with async_session_maker() as session:
        service = ProposalComparisonService(session)
        
        changes = await service.compare_for_proposal(
            workflow_id=UUID(workflow_id),
            expiring_doc_id=UUID(expiring_doc_id),
            renewal_doc_id=UUID(renewal_doc_id),
        )
        
        # Convert to dicts for Temporal serialization
        return [change.model_dump() for change in changes]
