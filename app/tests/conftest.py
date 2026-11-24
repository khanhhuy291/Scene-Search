import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def isolate_deployment_env_file(monkeypatch):
    """Developer credentials and deployment tuning must not alter unit test defaults."""
    from core.config import _BaseSettings, get_settings

    for model in _BaseSettings.__subclasses__():
        monkeypatch.setitem(model.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
