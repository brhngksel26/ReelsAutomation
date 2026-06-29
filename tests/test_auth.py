from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_and_me(client: AsyncClient, auth_headers: dict):
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["is_active"] is True
    assert body["profile"] is not None


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    email = f"duplicate_{datetime.now(timezone.utc).timestamp()}@example.com"
    payload = {"email": email, "password": "securepass123"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "badlogin@example.com", "password": "securepass123"},
    )
    login = await client.post(
        "/api/v1/auth/token",
        data={"username": "badlogin@example.com", "password": "wrongpassword"},
    )
    assert login.status_code == 401
