from pydantic import BaseModel, Field, HttpUrl

class WorkflowExtractionRequest(BaseModel):
    """Request model for starting document extraction workflow."""
    
    pdf_url: HttpUrl = Field(
        ...,
        description="HTTP/HTTPS URL of the PDF document to process",
        examples=["https://example.com/documents/policy.pdf"]
    )
