"""LLM Extraction child workflow."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import List, Optional, Dict

from app.schemas.product.shared_workflow_schemas import (
    ExtractionOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class ExtractionWorkflow:
    """Child workflow for LLM extraction."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        document_profile: Optional[Dict] = None,
        target_sections: Optional[List[str]] = None,
        target_entities: Optional[List[str]] = None,
    ) -> dict:
        """Execute the LLM extraction pipeline."""
        workflow.logger.info(
            f"Starting extraction workflow for document: {document_id}",
            extra={
                "workflow_id": workflow_id,
                "document_id": document_id,
                "has_document_profile": document_profile is not None,
                "target_sections": target_sections
            }
        )
        
        if not document_profile:
            raise ValueError("document_profile is required for ExtractionWorkflow")
            
        classification_result = self._convert_profile_to_classification(document_profile)
        
        extraction_result = await workflow.execute_activity(
            "extract_section_fields",
            args=[workflow_id, document_id, target_sections, target_entities],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        total_entities = len(extraction_result.get('all_entities', []))
        
        output = {
            "classification": classification_result,
            "extraction": extraction_result,
            "document_type": classification_result["document_type"],
            "total_entities": total_entities,
            "total_llm_calls": len(extraction_result.get('section_results', [])),
        }
        
        return validate_workflow_output(
            output,
            ExtractionOutputSchema,
            "ExtractionWorkflow"
        )
    
    def _convert_profile_to_classification(self, document_profile: Dict) -> Dict:
        """Convert document profile to classification result format."""
        return {
            "document_id": document_profile.get("document_id"),
            "document_type": document_profile.get("document_type", "unknown"),
            "document_subtype": document_profile.get("document_subtype"),
            "confidence": document_profile.get("confidence", 0.0),
            "section_boundaries": document_profile.get("section_boundaries", []),
            "page_section_map": document_profile.get("page_section_map", {}),
            "metadata": {
                **document_profile.get("metadata", {}),
                "source": "phase0_manifest",
            },
        }
