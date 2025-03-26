import pytest
import json
from httpx import AsyncClient
    


@pytest.mark.asyncio
async def test_trivial_service(http_client: AsyncClient, request_id: str):
    """Test that the TrivialExtProcService adds the x-extra-request-id header."""
    response = await http_client.get(f"/test-trivial?id={request_id}")

    assert response.status_code == 200

    # Check response body
    body = response.json()
    assert body["path"].startswith("/test-trivial")

    # Check that the x-extra-request-id was added in the upstream headers
    assert "x-request-id" in body["headers"]
    assert "x-extra-request-id" in body["headers"]
    assert body["headers"]["x-extra-request-id"] == body["headers"]["x-request-id"]


@pytest.mark.asyncio
async def test_timer_service(http_client: AsyncClient, request_id: str):
    """Test that the TimerExtProcService adds timing information in headers."""
    response = await http_client.get(f"/test-timer?id={request_id}")

    assert response.status_code == 200

    # Check response body
    body = response.json()
    assert body["path"].startswith("/test-timer")

    # The timing headers should be present in the echo server response
    # (showing they were added to the upstream request)
    assert "x-request-started" in body["headers"]

    # The timing headers should also be in the actual response headers
    assert "x-request-started" in response.headers
    assert "x-duration-ns" in response.headers


@pytest.mark.asyncio
async def test_echo_service(http_client: AsyncClient, request_id: str):
    """Test that the EchoExtProcService echoes back when requested."""
    test_data = {"test": "data"}

    # Without echo-only header, should reach the upstream
    response = await http_client.post(f"/test-echo?id={request_id}", json=test_data)
    assert response.status_code == 200
    body = response.json()
    assert body["path"].startswith("/test-echo")

    # With echo-only header, should short-circuit and return immediately
    response = await http_client.post(
        f"/test-echo?id={request_id}", headers={"x-echo-only": "true"}, json=test_data
    )
    assert response.status_code == 200

    # The echo service returns the original request back to us
    body = response.json()
    assert "body" in body
    # Our test data should be in the response body (as a string)
    test_data_str = json.dumps(test_data).replace(" ", "")
    body_content = body["body"].replace(" ", "")
    assert test_data_str in body_content


@pytest.mark.asyncio
async def test_digest_service(http_client: AsyncClient, request_id: str):
    """Test that the DigestExtProcService adds digest information."""
    test_data = {"test": "data"}

    response = await http_client.post(f"/test-digest?id={request_id}", json=test_data)

    assert response.status_code == 200

    # Check response body
    body = response.json()
    assert body["path"].startswith("/test-digest")

    # The digest header should be in both places
    assert "x-request-digest" in response.headers
    assert "x-request-digest" in body["headers"]

    # The digest should be a SHA-256 hash (64 hex chars)
    assert len(response.headers["x-request-digest"]) == 64


@pytest.mark.asyncio
async def test_decorated_service(http_client: AsyncClient, request_id: str):
    """Test that the DecoratedExtProcService behaves like the DigestExtProcService."""
    test_data = {"test": "data"}

    response = await http_client.post(
        f"/test-decorated?id={request_id}", json=test_data
    )

    assert response.status_code == 200

    # Check response body
    body = response.json()
    assert body["path"].startswith("/test-decorated")

    # The digest header should be in both places
    assert "x-request-digest" in response.headers
    assert "x-request-digest" in body["headers"]

    # The digest should be a SHA-256 hash (64 hex chars)
    assert len(response.headers["x-request-digest"]) == 64


@pytest.mark.asyncio
async def test_context_service(http_client: AsyncClient, request_id: str):
    """Test that the CtxExtProcService passes context correctly between phases."""
    context_id = f"test-context-id-{request_id}"

    response = await http_client.post(
        f"/test-context?id={request_id}",
        headers={"x-context-id": context_id},
        content=context_id,
    )

    assert response.status_code == 200

    # Check response body
    body = response.json()
    assert body["path"].startswith("/test-context")

    # Verify the context was passed correctly
    assert "x-context-id" in body["headers"]
    assert body["headers"]["x-context-id"] == context_id
