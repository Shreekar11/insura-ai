from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session as get_session
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.generated.query import GraphRAGRequest, GraphRAGResponse
from app.services.retrieval.graphrag_service import GraphRAGService
from app.services.workflow_service import WorkflowService
from app.services.user_service import UserService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()


async def get_graphrag_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> GraphRAGService:
    return GraphRAGService(db_session)


async def get_workflow_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> WorkflowService:
    return WorkflowService(db_session)


async def get_user_service(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> UserService:
    return UserService(db_session)


@router.post(
    "/{workflow_id}",
    response_model=GraphRAGResponse,
    summary="Execute GraphRAG query",
    operation_id="execute_query",
)
async def execute_query(
    workflow_id: UUID,
    request: GraphRAGRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    graphrag_service: Annotated[GraphRAGService, Depends(get_graphrag_service)],
) -> GraphRAGResponse:
    """
    Execute a GraphRAG query within a specific workflow context.
    
    This endpoint:
    1. Validates that the workflow exists and belongs to the user.
    2. Invokes the GraphRAG service to retrieve information and generate an answer.
    3. Returns the answer with citations and process metadata.
    """
    # 1. Validate user and workflow access
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    wf = await workflow_service.get_workflow_details(workflow_id, user.id)
    if not wf:
        LOGGER.warning(
            "Unauthorized or non-existent workflow query attempt",
            extra={"workflow_id": str(workflow_id), "user_id": str(user.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or access denied",
        )

    # 2. Invoke GraphRAG service
    try:
        response = await graphrag_service.query(
            workflow_id=workflow_id,
            request=request
        )
        return response
    except Exception as e:
        LOGGER.error(
            "GraphRAG query execution failed",
            extra={"workflow_id": str(workflow_id), "query": request.query[:100]},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}",
        )
