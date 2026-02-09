from datetime import datetime, timezone
from typing import Any, Optional, Dict
from uuid import uuid4
from fastapi import Request
# Use workflows generated schemas as the base for the common ApiResponse structure
from app.schemas.generated.workflows import ApiResponse, ResponseMeta, ErrorDetail

def create_api_response(
    data: Any,
    message: str = "Operation successful",
    status: bool = True,
    request: Optional[Request] = None,
    api_version: str = "v1"
) -> Dict[str, Any]:
    """Create a standardized API response as a dictionary.

    Returns a dict to be compatible with FastAPI's response_model=dict.
    """
    request_id = str(uuid4())
    if request and hasattr(request.state, "request_id"):
        request_id = request.state.request_id

    meta = ResponseMeta(
        timestamp=datetime.now(timezone.utc),
        request_id=request_id,
        api_version=api_version
    )

    # Ensure data is a dict as expected by ApiResponse
    data_dict: Dict[str, Any] = {}
    if isinstance(data, dict):
        data_dict = data
    elif hasattr(data, "model_dump"):
        data_dict = data.model_dump()
    elif isinstance(data, list):
        # If it's a list, we need to decide how to wrap it.
        # For 'total' + 'items' patterns, it might already be a dict.
        # Here we assume it's just a raw list.
        data_dict = {"items": [item.model_dump() if hasattr(item, "model_dump") else item for item in data]}
    elif data is None:
        data_dict = {}
    else:
        # Fallback for primitive types if they were passed
        data_dict = {"value": data}

    # Create ApiResponse and convert to dict for FastAPI compatibility
    response = ApiResponse(
        status=status,
        message=message,
        data=data_dict,
        meta=meta
    )
    return response.model_dump(mode="json")

def create_error_detail(
    title: str,
    status: int,
    detail: str,
    request: Optional[Request] = None,
    instance: Optional[str] = None
) -> ErrorDetail:
    """Create a standardized error detail (RFC 7807)."""
    request_id = str(uuid4())
    if request and hasattr(request.state, "request_id"):
        request_id = request.state.request_id
        
    return ErrorDetail(
        title=title,
        status=status,
        detail=detail,
        instance=instance or (request.url.path if request else None),
        request_id=request_id,
        timestamp=datetime.now(timezone.utc)
    )
