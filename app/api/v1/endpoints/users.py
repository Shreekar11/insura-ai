"""Authentication and user management endpoints.

This module provides API endpoints for user authentication,
profile management, and user-related operations.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.dependencies import get_user_service
from app.schemas.auth import CurrentUser, UserProfile
from app.services.user_service import UserService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

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

    Args:
        current_user: Current authenticated user from JWT
        user_service: User service for business logic

    Returns:
        UserProfile: User profile information

    Raises:
        HTTPException: If user profile cannot be retrieved
    """
    # Get user profile using Supabase user ID
    user_profile = await user_service.get_user_profile_by_supabase_id(current_user.id)

    LOGGER.info("User profile retrieved successfully")

    if not user_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found",
        )

    return user_profile


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

    Args:
        current_user: Current authenticated user from JWT
        user_service: User service for business logic

    Returns:
        UserProfile: Synced user profile information
    """
    user = await user_service.ensure_user_exists(current_user)

    LOGGER.info("User synced successfully")
    
    # Return profile from user object
    return UserProfile(
        id=user.supabase_user_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        created_at=user.created_at,
    )
