from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import BaseModel, metadata
from src.core.enums import ProfileTier
from src.core.permission import Permission

user_permissions = Table(
    "user_permissions",
    metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    profile: Mapped["Profile"] = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )
    permissions: Mapped[list["AuthPermission"]] = relationship(
        "AuthPermission",
        secondary=user_permissions,
        back_populates="users",
        lazy="selectin",
    )


class Profile(BaseModel):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tier: Mapped[ProfileTier] = mapped_column(
        String(20),
        default=ProfileTier.FREE,
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="profile")
    channels: Mapped[list["Channel"]] = relationship(
        "Channel",
        back_populates="profile",
        lazy="selectin",
    )


class AuthPermission(BaseModel):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission: Mapped[Permission] = mapped_column(String(50), nullable=False)

    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=user_permissions,
        back_populates="permissions",
    )
