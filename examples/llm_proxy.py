# LLMProxyExtProcService
#
# This example demonstrates how to proxy requests to an LLM API
# by modifying the request body and headers before forwarding to
# an upstream service. It:
# 1. Modifies the 'model' parameter in the request JSON
# 2. Replaces the Authorization header
# 3. Rewrites the host header
# 4. Allows streaming responses to flow through unmodified

import json
import logging
from typing import Dict

from envoy_extproc_sdk import BaseExtProcService, ext_api, serve
from grpc import ServicerContext

LLM_PROXY_HEADER = "x-llm-proxy"
TARGET_ENDPOINT = "/completions"

logger = logging.getLogger(__name__)


class LLMProxyExtProcService(BaseExtProcService):
    def process_request_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        # Skip processing if not specifically targeting completions endpoint
        if not request.get("path", "").endswith(TARGET_ENDPOINT):
            return response

        # Store content-type to check if JSON in body phase
        content_type = self.get_header(headers, "content-type")
        request["content_type"] = content_type

        # NOTE: We can't actually change the host/destination here in the ExtProc service.
        # The host rewriting must be done in the Envoy configuration via routes.
        # We'll add a header to simulate/test this capability, but in production,
        # you would need to configure Envoy routes to send traffic to the desired upstream.
        self.add_header(response, "x-target-host", "api.openai.com")

        # Replace the Authorization header
        auth_header = self.get_header(headers, "authorization")
        if auth_header:
            self.remove_header(response, "authorization")
            self.add_header(response, "authorization", "Bearer sk-proxy-key-replaced")
            logger.debug("Replaced Authorization header")

        # Add a marker header to indicate this request was proxied
        self.add_header(response, LLM_PROXY_HEADER, "true")

        return response

    def process_request_body(
        self,
        body: ext_api.HttpBody,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        if not request["path"].endswith(TARGET_ENDPOINT):
            return response

        if (
            request.get("content_type")
            and "application/json" in request["content_type"]
        ):
            try:
                body_str = body.body.decode("utf-8")
                json_body = json.loads(body_str)

                # Track modifications
                modified = False

                # Modify the 'model' parameter if present
                if "model" in json_body:
                    original_model = json_body["model"]
                    json_body["model"] = "gpt-4o"
                    modified = True
                    logger.debug(f"Changed model from {original_model} to gpt-4o")

                if modified:
                    new_body = json.dumps(json_body).encode("utf-8")

                    response.body_mutation.body = new_body

                    # Note: When working with Envoy ExtProc, we intentionally don't set the content-length header
                    # as Envoy uses transfer-encoding: chunked when body is modified.
                    self.add_header(response, "x-content-length", str(len(new_body)))
                    request["body_modified"] = True

            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Failed to decode JSON body")
                pass
        return response

    def process_response_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        if not request.get("path", "").endswith(TARGET_ENDPOINT):
            return response

        # Add proxy header to response
        self.add_header(response, LLM_PROXY_HEADER, "true")

        # Check if this is a streaming response
        content_type = self.get_header(headers, "content-type")
        if content_type and "text/event-stream" in content_type.lower():
            logger.debug(
                "Detected streaming response with content-type: %s", content_type
            )
        return response


if __name__ == "__main__":
    import logging

    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()]
    )

    serve(service=LLMProxyExtProcService())
