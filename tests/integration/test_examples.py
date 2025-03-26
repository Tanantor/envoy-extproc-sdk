import json

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_trivial_service(http_client: AsyncClient, request_id: str):
    """Test that the TrivialExtProcService adds the x-extra-request-id header."""
    response = await http_client.get(f"/test-trivial?id={request_id}")

    assert response.status_code == 200

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
    # TODO: CHeck this raises StopRequestProcessing exception in logs
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

    response = await http_client.post(f"/test-decorated?id={request_id}", json=test_data)

    assert response.status_code == 200

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

    body = response.json()
    assert body["path"].startswith("/test-context")

    # Verify the context was passed correctly
    assert "x-context-id" in body["headers"]
    assert body["headers"]["x-context-id"] == context_id


# @pytest.mark.asyncio
# async def test_body_modify_service(http_client: AsyncClient, request_id: str):
#     """Test that the BodyModifyExtProcService correctly modifies the JSON request body."""
#     test_data = {"user_id": "12345", "name": "test-user", "other_field": "unchanged"}

#     response = await http_client.post(
#         f"/body-modify?id={request_id}",
#         json=test_data,
#         headers={"content-type": "application/json"},
#     )

#     assert response.status_code == 200

#     body = response.json()
#     assert body["path"].startswith("/body-modify")

#     # The x-body-modified header should be present in the response headers
#     assert "x-body-modified" in response.headers
#     assert response.headers["x-body-modified"] == "true"

#     # Check that the headers were also added to the upstream request
#     assert "x-body-modified" in body["headers"]
#     assert body["headers"]["x-body-modified"] == "true"

#     # The body received by the echo server should have the modifications we made
#     # The echo server should return the modified body back to us in its "body" field
#     received_body = body["body"]
#     print("received_body", received_body)

#     if isinstance(received_body, str):
#         try:
#             received_body = json.loads(received_body)
#         except json.JSONDecodeError as e:
#             print(f"Failed to parse JSON body: {e}")
#             assert False, f"Failed to parse JSON body: {e}, raw body: {received_body}"

#     # Check that the key was renamed from user_id to userId
#     assert "userId" in received_body
#     assert "user_id" not in received_body
#     assert received_body["userId"] == "12345"

#     # Check that the name was modified with a prefix
#     assert received_body["name"].startswith("modified-")
#     assert received_body["name"] == "modified-test-user"

#     # Check that other fields were unchanged
#     assert received_body["other_field"] == "unchanged"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model,expected_route,expected_provider_model",
    [
        ("gpt-3.5-turbo", "openai", "gpt-4o"),
        ("claude-3.5-sonnet", "anthropic", "claude-3.7-sonnet"),
    ],
)
async def test_llm_proxy_service_streaming(
    http_client: AsyncClient,
    request_id: str,
    model: str,
    expected_route: str,
    expected_provider_model: str,
):
    """Test that the LLMProxyExtProcService correctly handles streaming responses and routes to the right provider."""
    test_data = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
    }

    async with http_client.stream(
        "POST",
        "/completions",
        json=test_data,
        headers={
            "content-type": "application/json",
            "authorization": "Bearer test-key",
            "x-request-id": request_id,
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"].lower()

        # Check proxy headers are present
        assert "x-llm-proxy" in response.headers
        assert response.headers["x-llm-proxy"] == "true"

        # Check model information is preserved in the response
        assert "x-original-model" in response.headers
        assert response.headers["x-original-model"] == model

        # # Check routing header was set
        assert "x-route-to" in response.headers
        assert response.headers["x-route-to"] == expected_route

        full_response = ""
        async for chunk in response.aiter_text():
            full_response += chunk
            if "[DONE]" in chunk:
                break

        print(f"Full response for {model}: {full_response[:200]}...")

        sse_chunks = [chunk for chunk in full_response.split("data:") if chunk.strip()]
        print(f"Found {len(sse_chunks)} SSE chunks")

        # We should have received at least 4 SSE chunks (role, content, finish, DONE)
        assert len(sse_chunks) > 3

        assert "assistant" in full_response
        assert "content" in full_response
        assert "[DONE]" in full_response

        # Verify the model was changed in the response chunks
        assert f'"model": "{expected_provider_model}"' in full_response
        assert f'"provider": "{expected_route}"' in full_response
