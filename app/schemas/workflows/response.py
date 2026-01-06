from pydantic import BaseModel, Field
from typing import List, Optional

class WorkflowExtractionResponse(BaseModel):
    """Response model for workflow extraction initiation."""
    
    workflow_id: str = Field(..., description="Unique workflow execution ID")
    documents: List[str] = Field(..., description="List of document IDs created")
    temporal_id: str = Field(..., description="Temporal workflow execution ID")
    status: str = Field(..., description="Current workflow status")
    message: str = Field(..., description="Human-readable status message")


class WorkflowStatusResponse(BaseModel):
    """Response model for workflow status query."""
    
    workflow_id: str = Field(..., description="Workflow execution ID")
    status: str = Field(..., description="Current workflow status")
    current_phase: Optional[str] = Field(None, description="Current processing phase")
    progress: float = Field(..., description="Progress percentage (0.0 to 1.0)")


class DocumentStageResponse(BaseModel):
    """Response model for document processing stages."""
    
    document_id: str = Field(..., description="Document ID")
    workflow_id: Optional[str] = Field(None, description="Associated workflow ID")
    stage_name: str = Field(..., description="Processing stage name")
    status: str = Field(..., description="Stage completion status")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")


class ErrorResponse(BaseModel):
    """Standardized error response model."""
    
    error: str = Field(..., description="Error type/code")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional error details")
