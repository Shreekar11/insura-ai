"""Phase 4: Tiered LLM Extraction child workflow.

This workflow orchestrates the two-tier LLM extraction pipeline:
- Tier 2: Section-level field extraction
- Tier 3: Cross-section validation and reconciliation

"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, Dict


@workflow.defn
class TieredExtractionWorkflow:
    """Child workflow for tiered LLM extraction."""
    
    @workflow.run
    async def run(
        self, 
        document_id: str,
        document_profile: Optional[Dict] = None,
    ) -> dict:
        """
        Execute the tiered LLM extraction pipeline.
        
        Tier 2: Section-level field extraction from super-chunks
        Tier 3: Cross-section validation and reconciliation
        
        Args:
            document_id: UUID of the document to extract from
            document_profile: Optional document profile from Phase 0 manifest.
                Contains: document_type, section_boundaries, page_section_map
            
        Returns:
            Dictionary with extraction and validation results
        """
        workflow.logger.info(
            f"Starting tiered extraction workflow for document: {document_id}",
            extra={
                "has_document_profile": document_profile is not None,
                "tier1_will_skip": document_profile is not None,
            }
        )
        
        # Check if we have a document profile from Phase 0
        if document_profile:
            workflow.logger.info(
                "[NEW DESIGN] Using document profile from Phase 0 manifest - Tier 1 LLM SKIPPED",
                extra={
                    "document_type": document_profile.get("document_type"),
                    "document_subtype": document_profile.get("document_subtype"),
                    "confidence": document_profile.get("confidence"),
                    "section_count": len(document_profile.get("section_boundaries", [])),
                    "page_section_map_size": len(document_profile.get("page_section_map", {})),
                    "tier1_skipped": True,
                }
            )
            # Convert document profile to classification result format for compatibility
            classification_result = self._convert_profile_to_classification(document_profile)
        else:
            workflow.logger.warning(
                extra={
                    "tier1_skipped": False,
                }
            )
            classification_result = await workflow.execute_activity(
                "classify_document_and_map_sections",
                document_id,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=5),
                    maximum_attempts=3,
                ),
            )
        
        workflow.logger.info(
            f"Classification ready: type={classification_result['document_type']}, "
            f"sections={len(classification_result['section_boundaries'])}",
            extra={
                "source": "manifest" if document_profile else "tier1_llm",
            }
        )
        
        # Tier 2: Section-Level Extraction
        workflow.logger.info("Tier 2: Extracting section-specific fields...")
        extraction_result = await workflow.execute_activity(
            "extract_section_fields",
            args=[document_id, classification_result],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        # Compute total_entities from all_entities list
        total_entities = len(extraction_result.get('all_entities', []))
        workflow.logger.info(
            f"Tier 2 complete: {total_entities} entities extracted, "
            f"{len(extraction_result.get('section_results', []))} sections processed"
        )
        
        # Tier 3: Cross-Section Validation
        workflow.logger.info("Tier 3: Validating and reconciling data...")
        validation_result = await workflow.execute_activity(
            "validate_and_reconcile_data",
            args=[document_id, classification_result, extraction_result],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        # Extract validation info safely
        validation_issues = validation_result.get('issues', [])
        validation_summary = validation_result.get('summary', {})
        data_quality_score = 1.0 - (
            validation_summary.get('errors', 0) * 0.1 + 
            validation_summary.get('warnings', 0) * 0.05
        )
        data_quality_score = max(0.0, min(1.0, data_quality_score))
        
        workflow.logger.info(
            f"Tier 3 complete: {len(validation_issues)} issues found, "
            f"data quality score: {data_quality_score:.2f}"
        )
        
        return {
            "classification": classification_result,
            "extraction": extraction_result,
            "validation": validation_result,
            "document_type": classification_result["document_type"],
            "total_entities": total_entities,
            "total_llm_calls": len(extraction_result.get('section_results', [])),
            "data_quality_score": data_quality_score,
            "is_valid": validation_result.get("is_valid", False),
            "tier1_skipped": document_profile is not None,
        }
    
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
                "tier1_llm_skipped": True,
            },
        }

