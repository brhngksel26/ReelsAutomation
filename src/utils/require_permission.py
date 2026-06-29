from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_handler import AuthHandler
from src.core.base_exception import (
    AuthenticationInvalidTokenError,
    AuthenticationValidationError,
)
from src.core.database import get_async_session
from src.core.permission import Permission
from src.cruds.auth import UserCrud
from src.models.auth import User


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())],
    access_token: Annotated[str | None, Cookie()] = None,
    db_session: AsyncSession = Depends(get_async_session),
) -> User:
    token = None
    if credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise AuthenticationValidationError("JWT token required for this endpoint")

    email = AuthHandler.decode_token(token, "access_token")

    if not email:
        raise AuthenticationInvalidTokenError("Could not validate credentials")

    user = await UserCrud().get_by_email_with_permissions(
        db=db_session,
        email=email,
    )

    if user is None:
        raise AuthenticationValidationError("Could not validate credentials.")

    if user.is_deleted or not user.is_active:
        raise AuthenticationValidationError("User is not active.")

    return user


def require_permission(permission: Permission):
    if not isinstance(permission, Permission):
        raise HTTPException(
            status_code=403,
            detail="require_permission requires a Permission enum value",
        )

    async def dependency(
        user: User = Depends(get_current_user),
    ) -> User:
        if user is None or not user.permissions:
            raise HTTPException(
                status_code=403,
                detail="User does not have any permissions",
            )

        has_permission = any(
            user_permission.permission == permission.value
            for user_permission in user.permissions
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied to {permission.value}",
            )

        return user

    return dependency
