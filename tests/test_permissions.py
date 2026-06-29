import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_permissions(
    client: AsyncClient,
    db_session,
):
    from src.cruds.auth import UserCrud

    email = "noperm@example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "securepass123"},
    )
    assert reg.status_code == 201
    user = await UserCrud().get_by_email(db_session, email)
    from sqlalchemy import delete

    from src.models.auth import user_permissions

    await db_session.execute(
        delete(user_permissions).where(user_permissions.c.user_id == user.id)
    )
    await db_session.commit()

    login = await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": "securepass123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 403
