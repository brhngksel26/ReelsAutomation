from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    get_auth_permission_crud,
    get_profile_crud,
    get_user_crud,
)
from src.core.auth_handler import AuthHandler
from src.core.config import settings
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.schemas.auth import RegisterIn, TokenOut, UserOut
from src.services.auth import authenticate_user, register_user

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/auth",
    tags=["auth"],
)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn,
    db: AsyncSession = Depends(get_async_session),
    user_crud=Depends(get_user_crud),
    profile_crud=Depends(get_profile_crud),
    auth_permission_crud=Depends(get_auth_permission_crud),
):
    user = await register_user(
        db,
        data,
        user_crud=user_crud,
        profile_crud=profile_crud,
        auth_permission_crud=auth_permission_crud,
    )
    return user


@router.post("/token", response_model=TokenOut)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_async_session),
    user_crud=Depends(get_user_crud),
):
    user = await authenticate_user(
        db,
        form_data.username,
        form_data.password,
        user_crud=user_crud,
    )
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = AuthHandler.encode_token(
        user.email,
        "access_token",
        {"minutes": int(settings.ACCESS_TOKEN_EXPIRE_MINUTES)},
    )
    return TokenOut(access_token=access_token)
