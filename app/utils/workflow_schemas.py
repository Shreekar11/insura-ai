"""Pydantic schemas for workflow output validation.

These schemas enforce strong contracts between workflow steps, ensuring
that each workflow's output matches expected structure and types.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from uuid import UUID


class PageAnalysisOutputSchema(BaseModel):
    """Schema for PageAnalysisWorkflow output validation."""
    
    document_id: str = Field(..., description="Document UUID as string")
    total_pages: int = Field(..., gt=0, description="Total number of pages")
    pages_to_process: List[int] = Field(..., description="Pages to process")
    pages_skipped: List[int] = Field(..., description="Pages to skip")
    processing_ratio: float = Field(..., ge=0.0, le=1.0, description="Processing ratio")
    document_profile: Optional[Dict[str, Any]] = Field(None, description="Document profile")
    page_section_map: Dict[int, str] = Field(default_factory=dict, description="Page to section mapping")
    
    @field_validator("pages_to_process", "pages_skipped")
    @classmethod
    def validate_page_lists(cls, v: List[int]) -> List[int]:
        """Ensure page numbers are positive."""
        if any(p < 1 for p in v):
            raise ValueError("Page numbers must be >= 1")
        return v
    
    @field_validator("document_profile")
    @classmethod
    def validate_document_profile(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate document profile structure if present."""
        if v is None:
            return v
        
        required_fields = ["document_type", "confidence", "section_boundaries"]
        missing = [f for f in required_fields if f not in v]
        if missing:
            raise ValueError(f"Document profile missing required fields: {missing}")
        
        if not isinstance(v.get("confidence"), (int, float)) or not (0.0 <= v["confidence"] <= 1.0):
            raise ValueError("Document profile confidence must be between 0.0 and 1.0")
        
        return v


class OCRExtractionOutputSchema(BaseModel):
    """Schema for OCRExtractionWorkflow output validation."""
    
    document_id: str = Field(..., description="Document UUID as string")
    page_count: int = Field(..., ge=0, description="Number of pages processed")
    pages_processed: List[int] = Field(..., description="List of processed page numbers")
    selective: bool = Field(..., description="Whether selective processing was used")
    has_section_metadata: bool = Field(..., description="Whether section metadata was stored")
    section_distribution: Optional[Dict[str, int]] = Field(None, description="Section distribution")
    
    @field_validator("pages_processed")
    @classmethod
    def validate_pages_processed(cls, v: List[int]) -> List[int]:
        """Ensure page numbers are positive."""
        if any(p < 1 for p in v):
            raise ValueError("Page numbers must be >= 1")
        return v


class TableExtractionOutputSchema(BaseModel):
    """Schema for TableExtractionWorkflow output validation."""
    
    tables_found: int = Field(..., ge=0, description="Number of tables detected")
    tables_processed: int = Field(..., ge=0, description="Number of tables processed")
    sov_items: int = Field(..., ge=0, description="Number of SOV items extracted")
    loss_run_claims: int = Field(..., ge=0, description="Number of Loss Run claims extracted")
    validation_passed: bool = Field(..., description="Whether validation passed")
    validation_errors: int = Field(..., ge=0, description="Number of validation errors")
    validation_results: List[Dict[str, Any]] = Field(default_factory=list, description="Validation results")
    errors: List[str] = Field(default_factory=list, description="Processing errors")


class HybridChunkingOutputSchema(BaseModel):
    """Schema for HybridChunkingWorkflow output validation."""
    
    chunk_count: int = Field(..., ge=0, description="Total number of chunks")
    super_chunk_count: int = Field(..., ge=0, description="Total number of super-chunks")
    sections_detected: List[str] = Field(..., description="List of detected section types")
    section_stats: Dict[str, int] = Field(..., description="Statistics per section")
    total_tokens: int = Field(..., ge=0, description="Total tokens across all chunks")
    avg_tokens_per_chunk: float = Field(..., ge=0.0, description="Average tokens per chunk")
    section_source: str = Field(..., description="Source of section information")


class TieredExtractionOutputSchema(BaseModel):
    """Schema for TieredExtractionWorkflow output validation."""
    
    classification: Dict[str, Any] = Field(..., description="Classification result")
    extraction: Dict[str, Any] = Field(..., description="Extraction result")
    validation: Dict[str, Any] = Field(..., description="Validation result")
    document_type: str = Field(..., description="Document type")
    total_entities: int = Field(..., ge=0, description="Total entities extracted")
    total_llm_calls: int = Field(..., ge=0, description="Total LLM calls made")
    data_quality_score: float = Field(..., ge=0.0, le=1.0, description="Data quality score")
    is_valid: bool = Field(..., description="Whether extraction is valid")
    tier1_skipped: bool = Field(..., description="Whether Tier 1 LLM was skipped")
    
    @field_validator("classification", "extraction", "validation")
    @classmethod
    def validate_result_dicts(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure result dictionaries are not empty."""
        if not isinstance(v, dict):
            raise ValueError("Result must be a dictionary")
        return v


class EntityResolutionOutputSchema(BaseModel):
    """Schema for EntityResolutionWorkflow output validation."""
    
    entity_count: int = Field(..., ge=0, description="Number of canonical entities")
    relationship_count: int = Field(..., ge=0, description="Number of relationships extracted")


def validate_workflow_output(
    output: Dict[str, Any],
    schema_class: type[BaseModel],
    workflow_name: str
) -> Dict[str, Any]:
    """Validate workflow output against schema.
    
    Args:
        output: Workflow output dictionary
        schema_class: Pydantic schema class to validate against
        workflow_name: Name of workflow for error messages
        
    Returns:
        Validated output dictionary
        
    Raises:
        ValueError: If validation fails
    """
    try:
        validated = schema_class(**output)
        return validated.model_dump()
    except Exception as e:
        error_msg = f"Schema validation failed for {workflow_name}: {str(e)}"
        raise ValueError(error_msg) from e

