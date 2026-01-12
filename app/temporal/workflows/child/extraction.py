"""LLM Extraction child workflow.

This workflow orchestrates the LLM extraction pipeline:
- Section-level field extraction

"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import List, Optional, Dict

from app.utils.workflow_schemas import (
    ExtractionOutputSchema,
    validate_workflow_output,
)


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
        """
        Execute the LLM extraction pipeline.
        
        Section-level field extraction from super-chunks
        
        Args:
            document_id: UUID of the document to extract from
            document_profile: Optional document profile from Processed workflow.
                Contains: document_type, section_boundaries, page_section_map
            target_sections: Optional list of sections to extract fields from.
            target_entities: Optional list of entities to normalize/extract.
            
        Returns:
            Dictionary with extraction and validation results
        """
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
            workflow.logger.error("Missing document_profile in ExtractionWorkflow")
            raise ValueError("document_profile is required for ExtractionWorkflow")
            
        workflow.logger.info(
            "Processing document profile",
            extra={
                "document_type": document_profile.get("document_type"),
                "document_subtype": document_profile.get("document_subtype"),
                "confidence": document_profile.get("confidence"),
                "section_count": len(document_profile.get("section_boundaries", [])),
                "page_section_map_size": len(document_profile.get("page_section_map", {})),
            }
        )
        # Convert document profile to classification result format for compatibility
        classification_result = self._convert_profile_to_classification(document_profile)
        
        workflow.logger.info(
            f"Classification ready: type={classification_result['document_type']}, "
            f"sections={len(classification_result['section_boundaries'])}",
        )
        
        # Section-Level Extraction
        workflow.logger.info(f"Extracting section-specific fields (target_sections: {target_sections})...")
        extraction_result = await workflow.execute_activity(
            "extract_section_fields",
            args=[workflow_id, document_id, target_sections, target_entities],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        # Compute total_entities from all_entities list
        total_entities = len(extraction_result.get('all_entities', []))
        workflow.logger.info(
            f"Section-level extraction complete: {total_entities} entities extracted, "
            f"{len(extraction_result.get('section_results', []))} sections processed"
        )
        
        output = {
            "classification": classification_result,
            "extraction": extraction_result,
            "document_type": classification_result["document_type"],
            "total_entities": total_entities,
            "total_llm_calls": len(extraction_result.get('section_results', [])),
        }
        
        # Validate output against schema (fail fast if invalid)
        validated_output = validate_workflow_output(
            output,
            ExtractionOutputSchema,
            "ExtractionWorkflow"
        )
        
        workflow.logger.info("Extraction output validated against schema")
        
        return validated_output
    
    def _convert_profile_to_classification(
        self, 
        document_profile: Dict
    ) -> Dict:
        """Convert document profile to classification result format.
        
        This ensures backward compatibility with Tier 2 and Tier 3 activities
        that expect the classification result format.
        
        Args:
            document_profile: Document profile from Phase 0 manifest
            
        Returns:
            Classification result dictionary in the expected format
        """
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

