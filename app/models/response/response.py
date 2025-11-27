from pydantic import BaseModel, Field

class HealthCheckResponse(BaseModel):
    """Health check response model.

    Attributes:
        status: Service status
        version: Application version
        service: Service name
    """

    status: str = Field(
        default="healthy",
        description="Service health status",
        examples=["healthy", "unhealthy"],
    )
    version: str = Field(
        ...,
        description="Application version",
        examples=["0.1.0"],
    )
    service: str = Field(
        ...,
        description="Service name",
        examples=["Insurance AI - OCR Service"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "version": "0.1.0",
                    "service": "Insurance AI - OCR Service",
                }
            ]
        }
    }
