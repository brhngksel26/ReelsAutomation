from typing import Any, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_exception import CrudIntegrityError


class BaseCrudService:
    """Base CRUD service with common operations."""

    def __init__(self, model_class):
        self.model = model_class

    async def create(self, db: AsyncSession, data: dict) -> Any:
        """Create a new record."""
        try:
            instance = self.model(**data)
            db.add(instance)
            await db.flush()
            await db.refresh(instance)
            return instance
        except IntegrityError as e:
            await db.rollback()
            raise CrudIntegrityError(f"Integrity error: {str(e)}") from e

    async def get(self, db: AsyncSession, **filters) -> Optional[Any]:
        """Get a single record by filters."""
        conditions = [
            getattr(self.model, field) == value
            for field, value in filters.items()
            if hasattr(self.model, field) and value is not None
        ]

        if not conditions:
            return None

        result = await db.execute(select(self.model).where(and_(*conditions)))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, id: int) -> Optional[Any]:
        """Get a record by ID."""
        return await db.get(self.model, id)

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters
    ) -> List[Any]:
        """Get multiple records with pagination and filters."""
        query = select(self.model)

        # Apply filters
        conditions = [
            getattr(self.model, field) == value
            for field, value in filters.items()
            if hasattr(self.model, field) and value is not None
        ]

        if conditions:
            query = query.where(and_(*conditions))

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return result.scalars().all()

    async def update(self, db: AsyncSession, id: int, data: dict) -> Optional[Any]:
        """Update a record by ID."""
        instance = await self.get_by_id(db, id)
        if not instance:
            return None

        for key, value in data.items():
            if hasattr(instance, key) and value is not None:
                setattr(instance, key, value)

        await db.flush()
        await db.refresh(instance)
        return instance

    async def delete(self, db: AsyncSession, id: int) -> bool:
        """Soft delete a record by ID."""
        instance = await self.get_by_id(db, id)
        if not instance:
            return False

        if hasattr(instance, "is_deleted"):
            instance.is_deleted = True
        else:
            await db.delete(instance)

        await db.flush()
        return True

    async def hard_delete(self, db: AsyncSession, id: int) -> bool:
        """Hard delete a record by ID."""
        instance = await self.get_by_id(db, id)
        if not instance:
            return False

        await db.delete(instance)
        await db.flush()
        return True

    async def count(self, db: AsyncSession, **filters) -> int:
        """Count records with optional filters."""
        query = select(self.model)

        conditions = [
            getattr(self.model, field) == value
            for field, value in filters.items()
            if hasattr(self.model, field) and value is not None
        ]

        if conditions:
            query = query.where(and_(*conditions))

        result = await db.execute(query)
        return len(result.scalars().all())
