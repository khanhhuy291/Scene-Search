import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/chat", "/api/v1/status"])
async def test_template_routes_are_not_exposed(client, path):
    response = await client.get(path)
    assert response.status_code == 404
