"""Proposal Generation Core Workflow - Child workflow for comparison, LLM, and PDF generation."""

from datetime import timedelta
from typing import Dict, List, Any
from uuid import UUID
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.schemas.product.proposal import Proposal


@workflow.defn
class ProposalGenerationCoreWorkflow:
    """Child workflow that handles comparison, narrative generation, and PDF assembly.
    
    This workflow is called after all documents have been processed through
    the shared stage workflows (Processed, Extracted, Enriched, Summarized).
    """

    @workflow.run
    async def run(
        self,
        workflow_id: str,
        document_ids: List[str],
        workflow_definition_id: str,
    ) -> Dict[str, Any]:
        """Run the core proposal generation logic.
        
        Args:
            workflow_id: Parent workflow ID
            document_ids: List of document IDs (exactly 2)
            workflow_definition_id: Workflow definition ID
            
        Returns:
            Dict containing proposal result and PDF path
        """
        # Step 1: Detect document roles (expiring vs. renewal)
        roles = await workflow.execute_activity(
            "detect_document_roles_activity",
            args=[workflow_id, document_ids],
            start_to_close_timeout=timedelta(seconds=60),
        )
        
        expiring_doc_id = roles["expiring"]
        renewal_doc_id = roles["renewal"]
        
        # Step 2: Compare documents for proposal
        changes = await workflow.execute_activity(
            "compare_documents_for_proposal_activity",
            args=[workflow_id, expiring_doc_id, renewal_doc_id],
            start_to_close_timeout=timedelta(minutes=2),
        )
        
        # Step 3: Assemble proposal with LLM narratives
        proposal_data = await workflow.execute_activity(
            "assemble_proposal_activity",
            args=[{
                "workflow_id": workflow_id,
                "document_ids": document_ids,
                "changes": changes,
            }],
            start_to_close_timeout=timedelta(minutes=5),
        )
        
        # Step 4: Generate PDF
        pdf_path = await workflow.execute_activity(
            "generate_pdf_activity",
            args=[proposal_data],
            start_to_close_timeout=timedelta(minutes=3),
        )
        
        # Step 5: Persist proposal to database
        persist_result = await workflow.execute_activity(
            "persist_proposal_activity",
            args=[proposal_data, pdf_path],
            start_to_close_timeout=timedelta(seconds=60),
        )
        
        return {
            "status": "COMPLETED",
            "proposal_id": persist_result.get("id"),
            "pdf_path": pdf_path,
            "expiring_document_id": expiring_doc_id,
            "renewal_document_id": renewal_doc_id,
            "total_changes": len(changes) if changes else 0,
        }
