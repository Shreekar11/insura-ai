"""User service for business logic operations.

This module provides user management business logic,
acting as an intermediary between repositories and API endpoints.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUser, UserCreate, UserUpdate, UserResponse, UserProfile
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class UserService:
    """Service for user business logic operations."""

    def __init__(self, db_session: AsyncSession):
        """Initialize service with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.repository = UserRepository(db_session)

    async def get_user_by_id(self, user_id: UUID) -> Optional[UserResponse]:
        """Get user by internal ID.

        Args:
            user_id: Internal user ID

        Returns:
            User response data or None if not found
        """
        user = await self.repository.get_by_id(user_id)
        return UserResponse.model_validate(user) if user else None

    async def get_user_by_supabase_id(self, supabase_user_id: str) -> Optional[UserResponse]:
        """Get user by Supabase user ID.

        Args:
            supabase_user_id: Supabase user ID

        Returns:
            User response data or None if not found
        """
        user = await self.repository.get_by_supabase_id(supabase_user_id)
        return UserResponse.model_validate(user) if user else None

    async def get_user_profile(self, user_id: UUID) -> Optional[UserProfile]:
        """Get user profile information.

        Args:
            user_id: Internal user ID

        Returns:
            User profile data or None if not found
        """
        user = await self.repository.get_by_id(user_id)
        if not user:
            return None

        return UserProfile(
            id=user.supabase_user_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            created_at=user.created_at,
            last_login=None,  # TODO: Add last login tracking if needed
        )

    async def get_user_profile_by_supabase_id(self, supabase_user_id: str) -> Optional[UserProfile]:
        """Get user profile information by Supabase user ID.

        Args:
            supabase_user_id: Supabase user ID

        Returns:
            User profile data or None if not found
        """
        user = await self.repository.get_by_supabase_id(supabase_user_id)
        if not user:
            return None

        return UserProfile(
            id=user.supabase_user_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            created_at=user.created_at,
            last_login=None,  # TODO: Add last login tracking if needed
        )

    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Create a new user.

        Args:
            user_data: User creation data

        Returns:
            Created user response data

        Raises:
            ValueError: If user with same Supabase ID or email already exists
        """
        # Check if user already exists
        existing_by_supabase_id = await self.repository.get_by_supabase_id(user_data.supabase_user_id)
        if existing_by_supabase_id:
            raise ValueError(f"User with Supabase ID {user_data.supabase_user_id} already exists")

        existing_by_email = await self.repository.get_by_email(user_data.email)
        if existing_by_email:
            raise ValueError(f"User with email {user_data.email} already exists")

        user = await self.repository.create(user_data)
        return UserResponse.model_validate(user)

    async def update_user(self, user_id: UUID, user_data: UserUpdate) -> Optional[UserResponse]:
        """Update an existing user.

        Args:
            user_id: Internal user ID
            user_data: User update data

        Returns:
            Updated user response data or None if not found
        """
        user = await self.repository.update(user_id, user_data)
        return UserResponse.model_validate(user) if user else None

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user.

        Args:
            user_id: Internal user ID

        Returns:
            True if user was deleted, False if not found
        """
        return await self.repository.delete(user_id)

    async def get_or_create_user_from_jwt(self, current_user: CurrentUser) -> User:
        """Get or create user from JWT claims.

        This is the primary method for handling users from authentication.
        It ensures we have a local user record for every authenticated user.

        Args:
            current_user: Current user from JWT claims

        Returns:
            User database instance (existing or newly created)
        """
        # Extract user info from JWT claims
        supabase_user_id = current_user.id
        email = current_user.email
        full_name = current_user.full_name
        role = current_user.role

        # Get or create user
        user = await self.repository.get_or_create_from_supabase(
            supabase_user_id=supabase_user_id,
            email=email,
            full_name=full_name,
            role=role
        )

        return user

    async def ensure_user_exists(self, current_user: CurrentUser) -> User:
        """Ensure a user exists for the given JWT claims.

        Similar to get_or_create_user_from_jwt but with more explicit naming.
        Use this when you need the database User object for relationships.

        Args:
            current_user: Current user from JWT claims

        Returns:
            User database instance
        """
        return await self.get_or_create_user_from_jwt(current_user)

    async def get_current_user_profile_data(self, current_user: CurrentUser) -> UserProfile:
        """Get profile for the currently authenticated user.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            UserProfile data
        """
        user = await self.get_or_create_user_from_jwt(current_user)
        return UserProfile(
            id=user.supabase_user_id,
            email=user.email,
            full_name=user.full_name or "",
            role=user.role,
            created_at=user.created_at,
        )

    async def sync_current_user(self, current_user: CurrentUser) -> UserProfile:
        """Sync the currently authenticated user with database.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            UserProfile data
        """
        user = await self.ensure_user_exists(current_user)
        return UserProfile(
            id=user.supabase_user_id,
            email=user.email,
            full_name=user.full_name or "",
            role=user.role,
            created_at=user.created_at,
        )
