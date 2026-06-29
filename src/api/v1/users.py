from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_profile_crud
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.models.auth import User
from src.schemas.auth import UserMeOut
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/users",
    tags=["users"],
)


@router.get("/me", response_model=UserMeOut)
async def get_me(
    user: User = Depends(require_permission(Permission.USER_READ)),
    db: AsyncSession = Depends(get_async_session),
    profile_crud=Depends(get_profile_crud),
):
    profile = await profile_crud.get_by_user_id(db, user.id)
    return UserMeOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        profile=profile,
    )
