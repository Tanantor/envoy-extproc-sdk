from typing import AsyncGenerator, AsyncIterator, TypeVar

from ..util.envoy import ext_api

T = TypeVar("T")


async def envoy_extproc_cycle(
    request_headers: ext_api.HttpHeaders = ext_api.HttpHeaders(),
    request_body: ext_api.HttpBody = ext_api.HttpBody(),
    request_trailers: ext_api.HttpTrailers = ext_api.HttpTrailers(),
    response_headers: ext_api.HttpHeaders = ext_api.HttpHeaders(),
    response_body: ext_api.HttpBody = ext_api.HttpBody(),
    response_trailers: ext_api.HttpTrailers = ext_api.HttpTrailers(),
) -> AsyncGenerator[ext_api.ProcessingRequest, None]:
    """Create a generator that can be used to test request cycles"""
    for msg in [
        ext_api.ProcessingRequest(request_headers=request_headers),
        ext_api.ProcessingRequest(request_body=request_body),
        ext_api.ProcessingRequest(request_trailers=request_trailers),
        ext_api.ProcessingRequest(response_headers=response_headers),
        ext_api.ProcessingRequest(response_body=response_body),
        ext_api.ProcessingRequest(response_trailers=response_trailers),
    ]:
        yield msg


# This class implements AsyncIterator to make mypy happy
class AsEnvoyExtProc(AsyncIterator[ext_api.ProcessingRequest]):
    def __init__(
        self,
        request_headers: ext_api.HttpHeaders = ext_api.HttpHeaders(),
        request_body: ext_api.HttpBody = ext_api.HttpBody(),
        request_trailers: ext_api.HttpTrailers = ext_api.HttpTrailers(),
        response_headers: ext_api.HttpHeaders = ext_api.HttpHeaders(),
        response_body: ext_api.HttpBody = ext_api.HttpBody(),
        response_trailers: ext_api.HttpTrailers = ext_api.HttpTrailers(),
    ) -> None:
        self.messages = [
            ext_api.ProcessingRequest(request_headers=request_headers),
            ext_api.ProcessingRequest(request_body=request_body),
            ext_api.ProcessingRequest(request_trailers=request_trailers),
            ext_api.ProcessingRequest(response_headers=response_headers),
            ext_api.ProcessingRequest(response_body=response_body),
            ext_api.ProcessingRequest(response_trailers=response_trailers),
        ]
        self._index = 0

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self) -> ext_api.ProcessingRequest:
        if self._index < len(self.messages):
            msg = self.messages[self._index]
            self._index += 1
            return msg
        raise StopAsyncIteration
