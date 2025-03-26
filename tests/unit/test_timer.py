from typing import Any, cast, Dict

from envoy_extproc_sdk import ext_api
from envoy_extproc_sdk.testing import (
    envoy_body,
    envoy_headers,
    envoy_set_headers_to_dict,
)
from examples import TimerExtProcService
from examples.timer import REQUEST_DURATION_HEADER, REQUEST_STARTED_HEADER
from google.protobuf.timestamp_pb2 import Timestamp
from grpc import ServicerContext
import pytest


@pytest.mark.parametrize(
    "headers",
    (
        envoy_headers(
            headers=[
                (":method", "get"),
                (":path", "/api/v0/resource"),
            ]
        ),
        envoy_headers(
            headers=[
                (":method", "get"),
                (":path", "/api/v0/resource"),
            ]
        ),
    ),
)
@pytest.mark.parametrize(
    "body",
    (envoy_body(),),
)
@pytest.mark.asyncio
async def test_timer_flow(headers: ext_api.HttpHeaders, body: ext_api.HttpBody) -> None:

    request: Dict[str, Any] = {}

    P = TimerExtProcService()

    s = Timestamp()
    s.GetCurrentTime()

    response = ext_api.CommonResponse()
    response = await P.process_request_headers(
        headers, cast(ServicerContext, None), request, response
    )
    assert isinstance(response, ext_api.CommonResponse)

    _headers = envoy_set_headers_to_dict(response)
    assert _headers
    assert REQUEST_STARTED_HEADER in _headers

    response = ext_api.CommonResponse()
    response = await P.process_response_body(body, cast(ServicerContext, None), request, response)
    assert isinstance(response, ext_api.CommonResponse)

    _headers = envoy_set_headers_to_dict(response)
    assert _headers
    assert REQUEST_STARTED_HEADER in _headers
    assert REQUEST_DURATION_HEADER in _headers

    v = Timestamp()
    v.FromJsonString(_headers[REQUEST_STARTED_HEADER])
    assert s.ToNanoseconds() < v.ToNanoseconds()
