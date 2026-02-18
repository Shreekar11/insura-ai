from typing import Generic, TypeVar, Type, Optional, List, Any, Dict, Union
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError

from app.utils.logging import get_logger

# Define a generic type for SQLAlchemy models
ModelType = TypeVar("ModelType")

LOGGER = get_logger(__name__)


class BaseRepository(Generic[ModelType]):
    """Base repository implementing common CRUD operations.
    
    This class provides a standard interface for database interactions,
    reducing boilerplate code in specific repositories.
    """

    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """Initialize the repository.
        
        Args:
            session: SQLAlchemy async session
            model: The SQLAlchemy model class this repository manages
        """
        self.session = session
        self.model = model
        self.logger = LOGGER

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """Get a record by its ID.
        
        Args:
            id: The UUID of the record
            
        Returns:
            The record if found, None otherwise
        """
        try:
            query = select(self.model).where(self.model.id == id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error retrieving {self.model.__name__} by ID {id}: {str(e)}",
                exc_info=True
            )
            raise

    async def get_all(
        self, 
        skip: int = 0, 
        limit: int = 200,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """Get all records with optional pagination and filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of field_name: value to filter by
            
        Returns:
            List of records
        """
        try:
            query = select(self.model)
            
            if filters:
                for field, value in filters.items():
                    if hasattr(self.model, field):
                        query = query.where(getattr(self.model, field) == value)
            
            query = query.offset(skip).limit(limit)
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error retrieving all {self.model.__name__}: {str(e)}",
                exc_info=True
            )
            raise

    async def create(self, **kwargs) -> ModelType:
        """Create a new record.
        
        Args:
            **kwargs: Fields and values for the new record
            
        Returns:
            The created record
        """
        try:
            instance = self.model(**kwargs)
            self.session.add(instance)
            await self.session.flush()
            await self.session.commit()
            return instance
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error creating {self.model.__name__}: {str(e)}",
                exc_info=True
            )
            raise

    async def update(self, id: UUID, **kwargs) -> Optional[ModelType]:
        """Update an existing record.
        
        Args:
            id: The UUID of the record to update
            **kwargs: Fields and values to update
            
        Returns:
            The updated record if found, None otherwise
        """
        try:
            # Check if record exists
            instance = await self.get_by_id(id)
            if not instance:
                return None
            
            # Update fields
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            
            # Update updated_at if it exists
            if hasattr(instance, "updated_at"):
                setattr(instance, "updated_at", datetime.now(timezone.utc))
                
            await self.session.flush()
            await self.session.commit()
            return instance
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error updating {self.model.__name__} {id}: {str(e)}",
                exc_info=True
            )
            raise

    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID.
        
        Args:
            id: The UUID of the record to delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            instance = await self.get_by_id(id)
            if not instance:
                return False
                
            await self.session.delete(instance)
            await self.session.flush()
            await self.session.commit()
            return True
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error deleting {self.model.__name__} {id}: {str(e)}",
                exc_info=True
            )
            raise
            
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records matching filters.
        
        Args:
            filters: Dictionary of field_name: value to filter by
            
        Returns:
            Count of matching records
        """
        try:
            query = select(func.count()).select_from(self.model)
            
            if filters:
                for field, value in filters.items():
                    if hasattr(self.model, field):
                        query = query.where(getattr(self.model, field) == value)
                        
            result = await self.session.execute(query)
            return result.scalar_one()
        except SQLAlchemyError as e:
            self.logger.error(
                f"Error counting {self.model.__name__}: {str(e)}",
                exc_info=True
            )
            raise
