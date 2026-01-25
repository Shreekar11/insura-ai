from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.core.auth import get_current_user
from app.core.dependencies import get_user_service
from app.schemas.auth import CurrentUser
from app.schemas.generated.users import UserProfile, ApiResponse
from app.services.user_service import UserService
from app.utils.logging import get_logger
from app.utils.responses import create_api_response

LOGGER = get_logger(__name__)

router = APIRouter()

@router.get(
    "/whoami",
    response_model=ApiResponse,
    summary="Get current user profile",
    description="Get the current authenticated user's profile information",
    operation_id="get_current_user_profile",
)
async def get_current_user_profile(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    """Get current user profile."""
    LOGGER.info(f"User profile retrieved for user: {current_user.id}")
    profile_data = await user_service.get_current_user_profile_data(current_user)
    
    return create_api_response(
        data=profile_data,
        message="User profile retrieved successfully",
        request=request
    )


@router.post(
    "/sync",
    response_model=ApiResponse,
    summary="Sync user with database",
    description="Sync the current authenticated user from Supabase with the database",
    operation_id="sync_user",
)
async def sync_user(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> ApiResponse:
    """Sync user with database."""
    LOGGER.info(f"Syncing user: {current_user.id}")
    synced_user = await user_service.sync_current_user(current_user)
    
    return create_api_response(
        data=synced_user,
        message="User synced successfully",
        request=request
    )


@router.get(
    "/logout",
    response_model=ApiResponse,
    summary="Logout user",
    description="Logs out the current user by clearing the session/token on the client side",
    operation_id="logout_user",
)
async def logout_user(request: Request) -> ApiResponse:
    """Logout user."""
    return create_api_response(
        data={"message": "Logged out successfully"},
        message="Logged out successfully",
        request=request
    )
