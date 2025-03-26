from typing import AsyncGenerator
import uuid

from httpx import AsyncClient
import pytest_asyncio


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    """Fixture for async HTTP client to test the Envoy ExtProc services through Envoy proxy."""
    async with AsyncClient(base_url="http://localhost:8080", timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture
def request_id():
    """Fixture to generate a unique request ID for tests."""
    return str(uuid.uuid4())
