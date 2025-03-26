from typing import cast, Dict, Optional

from envoy_extproc_sdk import BaseExtProcService
from envoy_extproc_sdk.testing import AsEnvoyExtProc, envoy_body, envoy_headers
from envoy_extproc_sdk.util.envoy import (
    EnvoyHeaderValue,
    EnvoyHeaderValueOption,
    ext_api,
)
from grpc import ServicerContext
import pytest


# Mock ServicerContext that only implements the needed methods for tests
class FakeServicerContext(ServicerContext):
    def abort(self, code, details):
        raise ValueError()

    def abort_with_status(self, status):
        raise ValueError()

    def add_callback(self, callback):
        pass

    def auth_context(self):
        return {}

    def cancel(self):
        pass

    def invocation_metadata(self):
        return {}

    def is_active(self):
        return True

    def peer(self):
        return ""

    def peer_identities(self):
        return []

    def peer_identity_key(self):
        return ""

    def send_initial_metadata(self, initial_metadata):
        pass

    def set_code(self, code):
        pass

    def set_compression(self, compression):
        pass

    def set_details(self, details):
        pass

    def set_trailing_metadata(self, trailing_metadata):
        pass

    def time_remaining(self):
        return 60.0

    def __eq__(self, other):
        return isinstance(other, FakeServicerContext)


def assert_empty_header_mutation(headers: ext_api.HeaderMutation) -> None:
    assert isinstance(headers, ext_api.HeaderMutation)
    assert len(headers.set_headers) == 0
    assert len(headers.remove_headers) == 0


def assert_empty_common_response(response: ext_api.CommonResponse) -> None:
    assert isinstance(response, ext_api.CommonResponse)
    assert response.status == ext_api.CommonResponse.ResponseStatus.CONTINUE
    assert_empty_header_mutation(response.header_mutation)


@pytest.mark.asyncio
async def test_base_service_process() -> None:
    p = BaseExtProcService()
    async for r in p.Process(AsEnvoyExtProc(), FakeServicerContext()):
        assert isinstance(r, ext_api.ProcessingResponse)


@pytest.mark.asyncio
async def test_abort_on_unknown() -> None:
    class BadProcessingRequest:
        def WhichOneof(self, name: str) -> str:
            return "this_is_not_in_spec"

        this_is_not_in_spec = ext_api.HttpHeaders()

    class BadStream:
        def __init__(self):
            self.messages = [BadProcessingRequest()]
            self._index = 0

        def __aiter__(self):
            self._index = 0
            return self

        async def __anext__(self):
            if self._index >= len(self.messages):
                raise StopAsyncIteration
            msg = self.messages[self._index]
            self._index += 1
            return msg

    p = BaseExtProcService()
    context = FakeServicerContext()
    responses = p.Process(BadStream(), context)

    with pytest.raises(ValueError):
        async for r in responses:
            print(r)


def test_just_continue_response() -> None:
    p = BaseExtProcService()
    response = p.just_continue_response()
    assert_empty_common_response(response)


def test_just_continue_headers() -> None:
    p = BaseExtProcService()
    response = p.just_continue_headers()
    assert isinstance(response, ext_api.HeadersResponse)
    assert_empty_common_response(response.response)


def test_just_continue_body() -> None:
    p = BaseExtProcService()
    response = p.just_continue_body()
    assert isinstance(response, ext_api.BodyResponse)
    assert_empty_common_response(response.response)


def test_just_continue_trailers() -> None:
    p = BaseExtProcService()
    response = p.just_continue_trailers()
    assert isinstance(response, ext_api.TrailersResponse)
    assert_empty_header_mutation(response.header_mutation)


@pytest.mark.parametrize(
    "headers, name, result",
    (
        (envoy_headers([]), "empty", None),
        (envoy_headers([("empty", "header")]), "empty", "header"),
        (envoy_headers([("empty", "header")]), "empty", "header"),
        (envoy_headers([("first", "1"), ("second", "2")]), "second", "2"),
    ),
)
def test_get_header(
    headers: ext_api.HttpHeaders,
    name: str,
    result: Optional[str],
) -> None:
    p = BaseExtProcService()
    value = p.get_header(headers, name)
    assert isinstance(value, str) or value is None
    assert result == value


@pytest.mark.parametrize(
    "headers, names, results",
    (
        (
            envoy_headers(headers=[("first", "1"), ("second", "2")]),
            {"second": "second"},
            {"second": "2"},
        ),
        (
            envoy_headers(headers=[("first", "1"), ("second", "2")]),
            {"first": "first", "second": "second"},
            {"first": "1", "second": "2"},
        ),
        (
            envoy_headers(headers=[("first", "1"), ("second", "2")]),
            {"first": "second", "second": "first"},
            {"first": "2", "second": "1"},
        ),
        (
            envoy_headers(headers={"first": "1", "second": "2"}),
            {"first": "second", "second": "first"},
            {"first": "2", "second": "1"},
        ),
        (
            envoy_headers([("first", "1"), ("second", "2")]),
            {"empty": "empty"},
            {"empty": None},
        ),
    ),
)
def test_get_headers(
    headers: ext_api.HttpHeaders,
    names: Dict[str, str],
    results: Dict[str, str],
) -> None:
    p = BaseExtProcService()
    values = p.get_headers(headers, names)
    assert isinstance(values, dict)
    assert results == values


@pytest.mark.parametrize(
    "key, value",
    (
        ("X-Fake-Header", "value"),
        ("X-Other-Fake-Header", "eulav"),
    ),
)
def test_add_header(key: str, value: str) -> None:
    p = BaseExtProcService()
    response = p.just_continue_response()
    assert len(response.header_mutation.set_headers) == 0
    new_header = EnvoyHeaderValueOption(header=EnvoyHeaderValue(key=key, value=value))
    updated = p.add_header(response, key, value)
    assert isinstance(updated, ext_api.CommonResponse)
    assert len(response.header_mutation.set_headers) == 1
    assert new_header in updated.header_mutation.set_headers


@pytest.mark.parametrize(
    "key",
    (
        ("X-Fake-Header"),
        ("X-Other-Fake-Header"),
    ),
)
def test_remove_header(key: str) -> None:
    p = BaseExtProcService()
    response = p.just_continue_response()
    assert len(response.header_mutation.remove_headers) == 0
    updated = p.remove_header(response, key)
    assert isinstance(updated, ext_api.CommonResponse)
    assert len(response.header_mutation.remove_headers) == 1
    assert key in response.header_mutation.remove_headers


@pytest.mark.parametrize(
    "headers",
    (envoy_headers(),),
)
@pytest.mark.asyncio
async def test_process_request_headers(headers: ext_api.HttpHeaders) -> None:
    p = BaseExtProcService()
    response = ext_api.CommonResponse()
    response = await p.process_request_headers(headers, cast(ServicerContext, None), {}, response)
    assert isinstance(response, ext_api.CommonResponse)


@pytest.mark.parametrize(
    "headers",
    (envoy_headers(),),
)
@pytest.mark.asyncio
async def test_process_response_headers(headers: ext_api.HttpHeaders) -> None:
    p = BaseExtProcService()
    response = ext_api.CommonResponse()
    response = await p.process_response_headers(headers, cast(ServicerContext, None), {}, response)
    assert isinstance(response, ext_api.CommonResponse)


@pytest.mark.parametrize(
    "body",
    (envoy_body(),),
)
@pytest.mark.asyncio
async def test_process_request_body(body: ext_api.HttpBody) -> None:
    p = BaseExtProcService()
    response = ext_api.CommonResponse()
    response = await p.process_request_body(body, cast(ServicerContext, None), {}, response)
    assert isinstance(response, ext_api.CommonResponse)


@pytest.mark.parametrize(
    "body",
    (envoy_body(),),
)
@pytest.mark.asyncio
async def test_process_response_body(body: ext_api.HttpBody) -> None:
    p = BaseExtProcService()
    response = ext_api.CommonResponse()
    response = await p.process_response_body(body, cast(ServicerContext, None), {}, response)
    assert isinstance(response, ext_api.CommonResponse)


@pytest.mark.parametrize(
    "trailers",
    (ext_api.HttpTrailers(),),
)
@pytest.mark.asyncio
async def test_process_request_trailers(trailers: ext_api.HttpTrailers) -> None:
    p = BaseExtProcService()
    response = ext_api.TrailersResponse(header_mutation=ext_api.HeaderMutation())
    response = await p.process_request_trailers(trailers, cast(ServicerContext, None), {}, response)
    assert isinstance(response, ext_api.TrailersResponse)


@pytest.mark.parametrize(
    "trailers",
    (ext_api.HttpTrailers(),),
)
@pytest.mark.asyncio
async def test_process_response_trailers(trailers: ext_api.HttpTrailers) -> None:
    p = BaseExtProcService()
    response = ext_api.TrailersResponse(header_mutation=ext_api.HeaderMutation())
    response = await p.process_response_trailers(
        trailers, cast(ServicerContext, None), {}, response
    )
    assert isinstance(response, ext_api.TrailersResponse)
