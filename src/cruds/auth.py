from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.base_crud import BaseCrudService
from src.core.permission import Permission
from src.models.auth import AuthPermission, Profile, User, user_permissions


class UserCrud(BaseCrudService):
    def __init__(self):
        super().__init__(User)

    async def get_by_email(self, db: AsyncSession, email: str) -> User | None:
        result = await db.execute(
            select(User).where(
                and_(User.email == email, User.is_deleted.is_(False)),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email_with_permissions(
        self,
        db: AsyncSession,
        email: str,
    ) -> User | None:
        result = await db.execute(
            select(User)
            .options(selectinload(User.permissions))
            .where(and_(User.email == email, User.is_deleted.is_(False)))
        )
        return result.scalar_one_or_none()

    async def assign_permissions(
        self,
        db: AsyncSession,
        user_id: int,
        permission_ids: list[int],
    ) -> None:
        if not permission_ids:
            return
        await db.execute(
            insert(user_permissions),
            [{"user_id": user_id, "permission_id": pid} for pid in permission_ids],
        )
        await db.flush()


class ProfileCrud(BaseCrudService):
    def __init__(self):
        super().__init__(Profile)

    async def get_by_user_id(self, db: AsyncSession, user_id: int) -> Profile | None:
        return await self.get(db, user_id=user_id, is_deleted=False)


class AuthPermissionCrud(BaseCrudService):
    def __init__(self):
        super().__init__(AuthPermission)

    async def get_by_permission(
        self,
        db: AsyncSession,
        permission: Permission,
    ) -> AuthPermission | None:
        return await self.get(db, permission=permission.value, is_deleted=False)

    async def get_default_permissions(self, db: AsyncSession) -> list[AuthPermission]:
        from src.core.permission import DEFAULT_FREE_TIER_PERMISSIONS

        permission_values = [p.value for p in DEFAULT_FREE_TIER_PERMISSIONS]
        result = await db.execute(
            select(AuthPermission).where(
                and_(
                    AuthPermission.permission.in_(permission_values),
                    AuthPermission.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    async def get_all_permissions(self, db: AsyncSession) -> list[AuthPermission]:
        result = await db.execute(
            select(AuthPermission).where(AuthPermission.is_deleted.is_(False))
        )
        return list(result.scalars().all())
