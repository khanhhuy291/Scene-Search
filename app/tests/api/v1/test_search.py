import pytest
from httpx import ASGITransport, AsyncClient
from api.main import app


@pytest.mark.asyncio
async def test_search_endpoint_contract():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/search?query=car+driving+street&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert "results" in data
        assert "total" in data
        assert data["query"] == "car driving street"
        assert isinstance(data["results"], list)
        if len(data["results"]) > 0:
            first = data["results"][0]
            assert "id" in first
            assert "video_id" in first
            assert "score" in first
            assert "video_url" in first
            assert "description" in first
