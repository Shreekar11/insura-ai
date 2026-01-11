"""Repository for user data access operations.

This module provides data access operations for user management,
following the repository pattern for clean separation of concerns.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.schemas.auth import UserCreate, UserUpdate, UserResponse
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class UserRepository:
    """Repository for User entity operations."""

    def __init__(self, db_session: AsyncSession):
        """Initialize repository with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db_session = db_session

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by internal ID.

        Args:
            user_id: Internal user ID

        Returns:
            User instance or None if not found
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_supabase_id(self, supabase_user_id: str) -> Optional[User]:
        """Get user by Supabase user ID.

        Args:
            supabase_user_id: Supabase user ID

        Returns:
            User instance or None if not found
        """
        stmt = select(User).where(User.supabase_user_id == supabase_user_id)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address.

        Args:
            email: User email address

        Returns:
            User instance or None if not found
        """
        stmt = select(User).where(User.email == email)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user_data: UserCreate) -> User:
        """Create a new user.

        Args:
            user_data: User creation data

        Returns:
            Created User instance
        """
        user = User(
            supabase_user_id=user_data.supabase_user_id,
            email=user_data.email,
            full_name=user_data.full_name,
            role=user_data.role,
        )

        self.db_session.add(user)
        await self.db_session.flush()  # Get the ID without committing

        LOGGER.info(f"Created user: {user.id} ({user.email})")
        return user

    async def update(self, user_id: UUID, user_data: UserUpdate) -> Optional[User]:
        """Update an existing user.

        Args:
            user_id: Internal user ID
            user_data: User update data

        Returns:
            Updated User instance or None if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        # Update only provided fields
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db_session.flush()

        LOGGER.info(f"Updated user: {user.id}")
        return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user by ID.

        Args:
            user_id: Internal user ID

        Returns:
            True if user was deleted, False if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False

        await self.db_session.delete(user)
        await self.db_session.flush()

        LOGGER.info(f"Deleted user: {user_id}")
        return True

    async def get_or_create_from_supabase(
        self,
        supabase_user_id: str,
        email: str,
        full_name: Optional[str] = None,
        role: str = "user"
    ) -> User:
        """Get existing user or create new one from Supabase data.

        This is the primary method for handling users from JWT claims.
        It ensures we have a local user record for every Supabase user.

        Args:
            supabase_user_id: Supabase user ID
            email: User email
            full_name: User full name (optional)
            role: User role (defaults to "user")

        Returns:
            User instance (existing or newly created)
        """
        # Try to find existing user
        user = await self.get_by_supabase_id(supabase_user_id)
        if user:
            # Update user info if it has changed
            needs_update = (
                user.email != email or
                (full_name is not None and user.full_name != full_name)
            )

            if needs_update:
                update_data = UserUpdate(email=email, full_name=full_name)
                user = await self.update(user.id, update_data)
                LOGGER.info(f"Updated existing user from Supabase: {user.id}")

            return user

        # Create new user
        user_data = UserCreate(
            supabase_user_id=supabase_user_id,
            email=email,
            full_name=full_name,
            role=role
        )

        user = await self.create(user_data)
        LOGGER.info(f"Created new user from Supabase: {user.id}")

        return user
