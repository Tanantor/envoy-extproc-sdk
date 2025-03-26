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
TARGET_MODEL_HEADER = "x-target-model"
ROUTE_HEADER = "x-route-to"

# Model to destination mapping
MODEL_ROUTES = {
    "gpt-3.5-turbo": "openai",
    "gpt-4o": "openai",
    "claude-3.5-sonnet": "anthropic",
    "claude-3.7-sonnet": "anthropic",
    "default": "default_llm_provider",
}

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
                logger.debug(f"ORIGINAL BODY: {body_str}")
                json_body = json.loads(body_str)

                # Track modifications
                modified = False

                # Extract and process the 'model' parameter if present
                if "model" in json_body:
                    original_model = json_body["model"]
                    request["original_model"] = original_model

                    # Set routing headers based on the model
                    self.add_header(response, TARGET_MODEL_HEADER, original_model)
                    target_route = MODEL_ROUTES.get(
                        original_model, MODEL_ROUTES["default"]
                    )
                    self.add_header(response, ROUTE_HEADER, target_route)
                    # Clear the route cache for the current client request. 
                    # We modified headers that are used to calculate the route.
                    response.clear_route_cache = True

                    # Modify model parameter based on target route
                    if target_route == "openai":
                        json_body["model"] = "gpt-4o"
                    elif target_route == "anthropic":
                        json_body["model"] = "claude-3.7-sonnet"

                    modified = True
                    logger.info(
                        f"Routing {original_model} to {target_route} as {json_body['model']}"
                    )

                if modified:
                    new_body = json.dumps(json_body).encode("utf-8")
                    
                    # Print the modified body for debugging
                    logger.debug(f"MODIFIED BODY SENT: {new_body.decode('utf-8')}")

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

        # Add model information to response if available
        if "original_model" in request:
            self.add_header(response, "x-original-model", request["original_model"])

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
