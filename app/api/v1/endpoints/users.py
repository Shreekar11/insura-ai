from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.dependencies import get_user_service
from app.schemas.auth import CurrentUser
from app.schemas.generated.users import UserProfile
from app.services.user_service import UserService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter()

@router.get(
    "/whoami",
    response_model=UserProfile,
    summary="Get current user profile",
    description="Get the current authenticated user's profile information",
    operation_id="get_current_user_profile",
)
async def get_current_user_profile(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserProfile:
    """Get current user profile.

    This endpoint returns the profile information for the currently
    authenticated user, including their Supabase user ID, email,
    full name, role, and account creation date.
    """
    LOGGER.info(f"User profile retrieved for user: {current_user.id}")
    return await user_service.get_current_user_profile_data(current_user)


@router.post(
    "/sync",
    response_model=UserProfile,
    summary="Sync user with database",
    description="Sync the current authenticated user from Supabase with the database",
    operation_id="sync_user",
)
async def sync_user(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserProfile:
    """Sync user with database.

    This endpoint ensures that the currently authenticated user from
    Supabase has a corresponding record in the database.
    """
    LOGGER.info(f"Syncing user: {current_user.id}")
    return await user_service.sync_current_user(current_user)


@router.get(
    "/logout",
    summary="Logout user",
    description="Logs out the current user by clearing the session/token on the client side",
    operation_id="logout_user",
)
async def logout_user():
    """Logout user.
    
    Note: Token invalidation usually happens on the client side (deleting the token),
    but this endpoint can be used to perform any necessary server-side cleanup.
    """
    return {"message": "Logged out successfully", "status": "success"}
