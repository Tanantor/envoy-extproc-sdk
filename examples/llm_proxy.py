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
from logging import getLogger
from typing import Any, Dict

from envoy_extproc_sdk import BaseExtProcService, ext_api, serve
from grpc import ServicerContext


LLM_PROXY_HEADER = "x-llm-proxy"
TARGET_ENDPOINT = "/v1"
TARGET_MODEL_HEADER = "x-target-model"
ROUTE_HEADER = "x-route-to"

# Model to destination mapping - using container hostnames for Docker DNS resolution

MODEL_MAPPINGS: Dict[str, Any] = {
    "gpt-3.5-turbo": {
        "inference_provider_id": "openai",
        "inference_provider_url": "openai:80",
        "inference_provider_model": "gpt-4o",
    },
    "claude-3.5-sonnet": {
        "inference_provider_id": "anthropic",
        "inference_provider_url": "anthropic:80",
        "inference_provider_model": "claude-3.7-sonnet",
    },
    "default": {
        "inference_provider_id": "streaming",
        "inference_provider_url": "streaming:80",
        "inference_provider_model": "default-model",
    },
}

# Path rewrite mapping based on inference service provider
PATH_REWRITES: Dict[str, Dict[str, str]] = {
    "openai": {},
    "anthropic": {"/v1/chat/completions": "/v1/messages"},
}


class LLMProxyExtProcService(BaseExtProcService):
    async def process_request_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        # Skip processing if not specifically targeting v1 endpoint
        if not request.get("path", "").startswith(TARGET_ENDPOINT):
            return response

        # Store content-type to check if JSON in body phase
        content_type = self.get_header(headers, "content-type")
        request["content_type"] = content_type

        # Store the original path for possible rewriting later
        request["original_path"] = request.get("path", "")
        self.logger.debug(f"Setting original path context: {request['original_path']}")

        # Replace the Authorization header
        auth_header = self.get_header(headers, "authorization")
        if auth_header:
            self.remove_header(response, "authorization")
            self.add_header(response, "authorization", "Bearer sk-proxy-key-replaced")
            self.logger.debug("Replaced Authorization header")

        # Add a marker header to indicate this request was proxied
        self.add_header(response, LLM_PROXY_HEADER, "true")

        return response

    async def process_request_body(
        self,
        body: ext_api.HttpBody,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        original_path = request.get("original_path", "")
        if not original_path.startswith(TARGET_ENDPOINT):
            return response

        if (
            request.get("content_type")
            and "application/json" in request["content_type"]
        ):
            try:
                body_str = body.body.decode("utf-8")
                self.logger.debug(f"ORIGINAL BODY: {body_str}")
                json_body = json.loads(body_str)

                # Track modifications
                modified = False

                # Extract and process the 'model' parameter if present
                if "model" in json_body:
                    original_model = json_body["model"]
                    request["original_model"] = original_model

                    # Set routing headers based on the model
                    self.add_header(response, TARGET_MODEL_HEADER, original_model)
                    model_mapping = MODEL_MAPPINGS.get(
                        original_model, MODEL_MAPPINGS["default"]
                    )
                    target_route = model_mapping.get("inference_provider_url", "")
                    self.add_header(response, ROUTE_HEADER, target_route)

                    # We can't directly set host/authority headers,
                    # but Envoy will use x-route-to for host rewriting
                    # based on our route configuration's host_rewrite_header

                    # Save target route for path rewriting
                    request["target_route"] = target_route

                    # Clear the route cache for the current client request.
                    # We modified headers that are used to calculate the route.
                    response.clear_route_cache = True

                    # Modify model parameter based on target route
                    json_body["model"] = model_mapping.get(
                        "inference_provider_model", ""
                    )

                    modified = True
                    self.logger.info(
                        f"Routing {original_model} to {target_route} as {json_body['model']}"
                    )

                    # Check if we need to rewrite the path
                    path_rewrites = PATH_REWRITES.get(
                        model_mapping["inference_provider_id"], {}
                    )
                    for old_path, new_path in path_rewrites.items():
                        if old_path in original_path:
                            new_request_path = original_path.replace(old_path, new_path)
                            self.logger.info(
                                f"Rewriting path from {original_path} to {new_request_path}"
                            )
                            self.add_header(response, ":path", new_request_path)
                            request["path"] = new_request_path
                            break

                if modified:
                    new_body = json.dumps(json_body).encode("utf-8")

                    self.logger.debug(f"MODIFIED BODY SENT: {new_body.decode('utf-8')}")

                    response.body_mutation.body = new_body

                    # When working with Envoy ExtProc, we don't set the content-length header
                    # as Envoy uses transfer-encoding: chunked when body is modified.
                    self.add_header(response, "x-content-length", str(len(new_body)))
                    request["body_modified"] = True

            except (json.JSONDecodeError, UnicodeDecodeError):
                self.logger.warning("Failed to decode JSON body")
                pass
        return response

    async def process_response_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        original_path = request.get("original_path", "")
        if not original_path.startswith(TARGET_ENDPOINT):
            return response

        self.logger.debug(
            f"""Processing response headers for path: {original_path} 
            with context: {request} and headers: {headers}"""
        )
        # Add proxy header to response
        self.add_header(response, LLM_PROXY_HEADER, "true")

        # Add model information to response if available
        if "original_model" in request:
            self.add_header(response, "x-original-model", request["original_model"])

        # Add route information for testing purposes
        if "target_route" in request:
            self.add_header(response, "x-route-to", request["target_route"])

        if original_path != request.get("path", ""):
            self.add_header(response, "x-path-rewritten", "true")

        # Check if this is a streaming response (for demo/debug purposes)
        content_type = self.get_header(headers, "content-type")
        if content_type and "text/event-stream" in content_type.lower():
            self.logger.debug(
                "Detected streaming response with content-type: %s", content_type
            )
        return response


def run_processing_server():
    logger = getLogger(__name__)
    logger.info("Starting LLM Proxy ExtProc service...")
    serve(service=LLMProxyExtProcService(logger=logger))


if __name__ == "__main__":
    run_processing_server()
