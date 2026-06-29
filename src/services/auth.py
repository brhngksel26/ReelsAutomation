from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_handler import AuthHandler
from src.core.base_exception import CrudIntegrityError
from src.core.deps import (
    get_auth_permission_crud,
    get_profile_crud,
    get_user_crud,
)
from src.core.enums import ProfileTier
from src.models.auth import User
from src.protocols.auth import (
    AuthPermissionRepository,
    ProfileRepository,
    UserRepository,
)
from src.schemas.auth import RegisterIn


async def register_user(
    db: AsyncSession,
    data: RegisterIn,
    *,
    user_crud: UserRepository | None = None,
    profile_crud: ProfileRepository | None = None,
    auth_permission_crud: AuthPermissionRepository | None = None,
) -> User:
    user_crud = user_crud or get_user_crud()
    profile_crud = profile_crud or get_profile_crud()
    auth_permission_crud = auth_permission_crud or get_auth_permission_crud()

    existing = await user_crud.get_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        user = await user_crud.create(
            db,
            {
                "email": data.email,
                "hashed_password": AuthHandler.get_password_hash(data.password),
                "is_active": True,
                "is_verified": False,
            },
        )
        await profile_crud.create(
            db,
            {
                "user_id": user.id,
                "first_name": data.first_name,
                "last_name": data.last_name,
                "tier": ProfileTier.FREE.value,
            },
        )
        permissions = await auth_permission_crud.get_default_permissions(db)
        if permissions:
            await user_crud.assign_permissions(
                db,
                user.id,
                [p.id for p in permissions],
            )
        return await user_crud.get_by_email_with_permissions(db, data.email)
    except CrudIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
    *,
    user_crud: UserRepository | None = None,
) -> User | None:
    user_crud = user_crud or get_user_crud()

    user = await user_crud.get_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not AuthHandler.verify_password(password, user.hashed_password):
        return None
    return user
