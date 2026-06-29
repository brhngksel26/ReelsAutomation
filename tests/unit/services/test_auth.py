from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.base_exception import CrudIntegrityError
from src.core.enums import ProfileTier
from src.core.permission import Permission
from src.schemas.auth import RegisterIn
from src.services.auth import register_user


def _make_user(
    *,
    user_id: int = 1,
    email: str = "new@example.com",
    permissions: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=email,
        hashed_password="hashed",
        is_active=True,
        is_verified=False,
        permissions=permissions or [],
    )


def _make_profile(*, profile_id: int = 10, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=profile_id,
        user_id=user_id,
        first_name="Ada",
        last_name="Lovelace",
        tier=ProfileTier.FREE.value,
    )


def _make_permission(*, permission_id: int, permission: Permission) -> SimpleNamespace:
    return SimpleNamespace(id=permission_id, permission=permission)


class FakeUserRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, SimpleNamespace] = {}
        self.users_by_id: dict[int, SimpleNamespace] = {}
        self.assigned_permissions: list[tuple[int, list[int]]] = []
        self._next_id = 1
        self._rollback_callbacks: list[callable] = []

    def register_rollback(self, callback: callable) -> None:
        self._rollback_callbacks.append(callback)

    def rollback(self) -> None:
        for callback in reversed(self._rollback_callbacks):
            callback()
        self._rollback_callbacks.clear()

    async def get_by_email(self, db, email: str) -> SimpleNamespace | None:
        return self.users_by_email.get(email)

    async def create(self, db, data: dict) -> SimpleNamespace:
        user_id = self._next_id
        self._next_id += 1
        user = _make_user(user_id=user_id, email=data["email"])
        user.hashed_password = data["hashed_password"]
        user.is_active = data["is_active"]
        user.is_verified = data["is_verified"]

        email = data["email"]
        self.users_by_email[email] = user
        self.users_by_id[user_id] = user

        def undo() -> None:
            self.users_by_email.pop(email, None)
            self.users_by_id.pop(user_id, None)

        self.register_rollback(undo)
        return user

    async def assign_permissions(
        self,
        db,
        user_id: int,
        permission_ids: list[int],
    ) -> None:
        self.assigned_permissions.append((user_id, permission_ids))

    async def get_by_email_with_permissions(
        self, db, email: str
    ) -> SimpleNamespace | None:
        user = self.users_by_email.get(email)
        if user is None:
            return None
        user.permissions = [
            _make_permission(permission_id=1, permission=Permission.USER_READ),
            _make_permission(permission_id=2, permission=Permission.CHANNEL_CREATE),
        ]
        return user


class FakeProfileRepository:
    def __init__(self, *, fail_on_create: bool = False) -> None:
        self.profiles_by_user_id: dict[int, SimpleNamespace] = {}
        self.fail_on_create = fail_on_create
        self._next_id = 1
        self._rollback_callbacks: list[callable] = []

    def register_rollback(self, callback: callable) -> None:
        self._rollback_callbacks.append(callback)

    def rollback(self) -> None:
        for callback in reversed(self._rollback_callbacks):
            callback()
        self._rollback_callbacks.clear()

    async def create(self, db, data: dict) -> SimpleNamespace:
        if self.fail_on_create:
            raise RuntimeError("profile create failed")

        profile_id = self._next_id
        self._next_id += 1
        profile = _make_profile(profile_id=profile_id, user_id=data["user_id"])
        profile.first_name = data["first_name"]
        profile.last_name = data["last_name"]
        profile.tier = data["tier"]

        user_id = data["user_id"]
        self.profiles_by_user_id[user_id] = profile

        def undo() -> None:
            self.profiles_by_user_id.pop(user_id, None)

        self.register_rollback(undo)
        return profile


class FakeAuthPermissionRepository:
    def __init__(self) -> None:
        self.default_permissions = [
            _make_permission(permission_id=1, permission=Permission.USER_READ),
            _make_permission(permission_id=2, permission=Permission.CHANNEL_CREATE),
        ]

    async def get_default_permissions(self, db) -> list[SimpleNamespace]:
        return self.default_permissions


@pytest.fixture
def register_data() -> RegisterIn:
    return RegisterIn(
        email="new@example.com",
        password="securepass123",
        first_name="Ada",
        last_name="Lovelace",
    )


@pytest.mark.asyncio
async def test_register_user_creates_user_profile_and_permissions(register_data):
    user_repo = FakeUserRepository()
    profile_repo = FakeProfileRepository()
    permission_repo = FakeAuthPermissionRepository()
    db = MagicMock()

    user = await register_user(
        db,
        register_data,
        user_crud=user_repo,
        profile_crud=profile_repo,
        auth_permission_crud=permission_repo,
    )

    assert user.email == register_data.email
    assert register_data.email in user_repo.users_by_email
    assert (
        user_repo.users_by_email[register_data.email].id
        in profile_repo.profiles_by_user_id
    )
    assert user_repo.assigned_permissions == [(1, [1, 2])]
    assert len(user.permissions) == 2


@pytest.mark.asyncio
async def test_register_user_rejects_duplicate_email(register_data):
    user_repo = FakeUserRepository()
    user_repo.users_by_email[register_data.email] = _make_user(
        email=register_data.email
    )
    profile_repo = FakeProfileRepository()
    permission_repo = FakeAuthPermissionRepository()

    with pytest.raises(HTTPException) as exc_info:
        await register_user(
            MagicMock(),
            register_data,
            user_crud=user_repo,
            profile_crud=profile_repo,
            auth_permission_crud=permission_repo,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email already registered"
    assert user_repo.assigned_permissions == []
    assert profile_repo.profiles_by_user_id == {}


@pytest.mark.asyncio
async def test_register_user_maps_integrity_error_to_conflict(register_data):
    user_repo = AsyncMock()
    user_repo.get_by_email.return_value = None
    user_repo.create.side_effect = CrudIntegrityError("duplicate key")
    profile_repo = FakeProfileRepository()
    permission_repo = FakeAuthPermissionRepository()

    with pytest.raises(HTTPException) as exc_info:
        await register_user(
            MagicMock(),
            register_data,
            user_crud=user_repo,
            profile_crud=profile_repo,
            auth_permission_crud=permission_repo,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "duplicate key"
    user_repo.assign_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_register_user_rollback_leaves_no_partial_state_on_profile_failure(
    register_data,
):
    user_repo = FakeUserRepository()
    profile_repo = FakeProfileRepository(fail_on_create=True)
    permission_repo = FakeAuthPermissionRepository()

    with pytest.raises(RuntimeError, match="profile create failed"):
        await register_user(
            MagicMock(),
            register_data,
            user_crud=user_repo,
            profile_crud=profile_repo,
            auth_permission_crud=permission_repo,
        )

    user_repo.rollback()
    profile_repo.rollback()

    assert user_repo.users_by_email == {}
    assert user_repo.users_by_id == {}
    assert profile_repo.profiles_by_user_id == {}
    assert user_repo.assigned_permissions == []
