# TimerExtProcService
#
# This ExternalProcessor "times" a request by storing a `Timer`
# object in the `request` object, sending an `x-request-started`
# header to upstream filters and targets, and using it in
# responding with both a `x-request-started` and a `x-duration-ns`
# header describing the duration of upstream processing. If used
# in practice, this would describe to a caller how long a request
# took minus, roughly, round-trip network time. This also demon-
# strates using _objects_ in the request context, as opposed to
# "primitive types" like bools, ints, or strings.

from typing import Dict

from envoy_extproc_sdk import BaseExtProcService, ext_api, serve
from envoy_extproc_sdk.util.timer import Timer
from grpc import ServicerContext

REQUEST_STARTED_HEADER = "X-Request-Started"
REQUEST_DURATION_HEADER = "X-Duration-Ns"


class TimerExtProcService(BaseExtProcService):
    """ "Global" request timer that provides request timing for
    any upstream filters (or services) as well as a duration
    (over upstreams) response header"""

    async def process_request_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        """Start a timer in the context, add a request started header"""
        request["timer"] = Timer().tic()
        self.add_header(response, REQUEST_STARTED_HEADER, request["timer"].started_iso())
        return response

    async def process_response_body(
        self,
        body: ext_api.HttpBody,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        """ "End" the timer in the context, add a response duration header"""
        timer = request["timer"].toc()
        self.add_header(response, REQUEST_STARTED_HEADER, timer.started_iso())
        self.add_header(response, REQUEST_DURATION_HEADER, str(timer.duration_ns()))
        return response


if __name__ == "__main__":

    import logging

    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()])

    serve(service=TimerExtProcService())
