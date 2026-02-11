from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session as get_session
from app.core.auth import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.generated.query import GraphRAGRequest, GraphRAGResponse
from app.schemas.query import WorkflowMessage
from app.services.retrieval.graphrag_service import GraphRAGService
from app.services.workflow_service import WorkflowService
from app.services.user_service import UserService
from app.repositories.workflow_repository import WorkflowQueryRepository
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


async def get_workflow_query_repository(
    db_session: Annotated[AsyncSession, Depends(get_session)]
) -> WorkflowQueryRepository:
    return WorkflowQueryRepository(db_session)


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
    query_repo: Annotated[WorkflowQueryRepository, Depends(get_workflow_query_repository)],
) -> GraphRAGResponse:
    """
    Execute a GraphRAG query within a specific workflow context.
    
    This endpoint:
    1. Validates that the workflow exists and belongs to the user.
    2. Persists the user's query.
    3. Invokes the GraphRAG service to retrieve information and generate an answer.
    4. Persists the model's response.
    5. Returns the answer with citations and process metadata.
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

    # 2. Persist user query
    try:
        await query_repo.create_query(
            workflow_id=workflow_id,
            role="user",
            content=request.query,
            additional_metadata={"intent_override": request.intent_override}
        )
    except Exception as e:
        LOGGER.error(
            "Failed to persist user query",
            extra={"workflow_id": str(workflow_id), "error": str(e)},
        )
    # 3. Invoke GraphRAG service
    try:
        response = await graphrag_service.query(
            workflow_id=workflow_id,
            request=request
        )
        
        # 4. Persist model response
        await query_repo.create_query(
            workflow_id=workflow_id,
            role="model",
            content=response.answer,
            additional_metadata={
                "citations_count": len(response.sources) if response.sources else 0,
                "latency_ms": response.metadata.latency_ms
            }
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


@router.get(
    "/{workflow_id}/messages",
    response_model=List[WorkflowMessage],
    summary="Get workflow chat history",
    operation_id="get_workflow_messages",
)
async def get_workflow_messages(
    workflow_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    workflow_service: Annotated[WorkflowService, Depends(get_workflow_service)],
    query_repo: Annotated[WorkflowQueryRepository, Depends(get_workflow_query_repository)],
) -> List[WorkflowMessage]:
    """Retrieve chat history for a specific workflow."""
    # Validate access
    user = await user_service.get_or_create_user_from_jwt(current_user)
    
    wf = await workflow_service.get_workflow_details(workflow_id, user.id)
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or access denied",
        )
        
    messages = await query_repo.get_by_workflow_id(workflow_id)
    return messages

