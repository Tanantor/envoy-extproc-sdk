from typing import Any, cast, Dict
from uuid import uuid4

from envoy_extproc_sdk import ext_api, StopRequestProcessing
from envoy_extproc_sdk.testing import envoy_body, envoy_headers
from envoy_extproc_sdk.util.envoy import EnvoyHttpStatusCode
from examples import EchoExtProcService
from grpc import ServicerContext
import pytest


@pytest.mark.parametrize(
    "headers",
    (
        envoy_headers(
            headers=[
                (":method", "get"),
                (":path", "/api/v0/resource"),
                ("x-request-id", str(uuid4())),
                ("x-echo-only", "true"),
            ]
        ),
        envoy_headers(
            headers=[
                (":method", "get"),
                (":path", "/api/v0/resource"),
                ("x-request=-id", str(uuid4())),
                ("authorization", str(uuid4())),
                ("x-echo-only", "true"),
            ]
        ),
    ),
)
@pytest.mark.parametrize(
    "body",
    (envoy_body(body="something"),),
)
@pytest.mark.asyncio
async def test_echo_flow(headers: ext_api.HttpHeaders, body: ext_api.HttpBody) -> None:

    request: Dict[str, Any] = {}

    P = EchoExtProcService()

    response = ext_api.CommonResponse()
    response = await P.process_request_headers(
        headers, cast(ServicerContext, None), request, response
    )
    assert isinstance(response, ext_api.CommonResponse)

    # respond immediately to body request
    response = ext_api.CommonResponse()
    with pytest.raises(StopRequestProcessing) as err:
        await P.process_request_body(body, cast(ServicerContext, None), request, response)

    immediate_response = err.value.response
    assert isinstance(immediate_response, ext_api.ImmediateResponse)
    assert immediate_response.status.code == EnvoyHttpStatusCode.OK
    # assert response.body == body.body # type mismatch - bytes/str

    # check headers?
