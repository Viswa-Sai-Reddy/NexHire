"""HTTP smoke: /health and /.well-known/jwks.json respond correctly."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_responds_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "db" in body
    assert "redis" in body


@pytest.mark.asyncio
async def test_jwks_served(client: AsyncClient) -> None:
    response = await client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert body["keys"][0]["kty"] == "RSA"
    assert body["keys"][0]["alg"] == "RS256"


@pytest.mark.asyncio
async def test_request_id_header_round_trips(client: AsyncClient) -> None:
    """Client-supplied UUID is echoed; non-UUID is replaced."""
    rid = "11111111-1111-1111-1111-111111111111"
    response = await client.get("/health", headers={"X-Request-Id": rid})
    assert response.headers["X-Request-Id"] == rid

    response = await client.get("/health", headers={"X-Request-Id": "not-a-uuid"})
    echoed = response.headers["X-Request-Id"]
    # Should be a fresh UUID (any UUID != the bad one).
    assert echoed != "not-a-uuid"
    assert len(echoed) == 36
