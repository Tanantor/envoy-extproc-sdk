# BodyModifyExtProcService
#
# This example demonstrates how to modify the JSON request body
# before it's forwarded to the upstream service. It:
# 1. Renames a key in the request JSON
# 2. Modifies the value of a key in the request JSON
# 3. Adds a header to indicate the body was modified

import json
from typing import Dict
import logging

from envoy_extproc_sdk import BaseExtProcService, ext_api, serve
from grpc import ServicerContext

BODY_MODIFIED_HEADER = "x-body-modified"

logger = logging.getLogger(__name__)

class BodyModifyExtProcService(BaseExtProcService):
    def process_request_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        # Skip processing if not specifically targeting this service via path
        if not request.get("path", "").startswith("/body-modify"):
            return response
            
        # Store content-type to check if JSON in body phase
        content_type = self.get_header(headers, "content-type")
        request["content_type"] = content_type
        return response

    def process_request_body(
        self,
        body: ext_api.HttpBody,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        if not request["path"].startswith("/body-modify"):
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

                # 1. Rename a key (e.g., 'user_id' -> 'userId')
                if "user_id" in json_body:
                    json_body["userId"] = json_body.pop("user_id")
                    modified = True

                # 2. Modify a value (e.g., add prefix to 'name' field)
                if "name" in json_body:
                    json_body["name"] = f"modified-{json_body['name']}"
                    modified = True

                if modified:
                    new_body = json.dumps(json_body).encode("utf-8")
                    
                    response.body_mutation.body = new_body
                    
                    # Note: When working with Envoy ExtProc, we intentionally don't set the content-length header
                    # as Envoy uses transfer-encoding: chunked when body is modified.
                    # Instead, we use x-content-length for our echo server to know the body size.
                    self.add_header(response, "x-content-length", str(len(new_body)))
                    
                    self.add_header(response, BODY_MODIFIED_HEADER, "true")
                    request["body_modified"] = True

            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Failed to decode JSON body")
                pass
        logger.debug(f"response: {response}")
        return response

    def process_response_headers(
        self,
        headers: ext_api.HttpHeaders,
        context: ServicerContext,
        request: Dict,
        response: ext_api.CommonResponse,
    ) -> ext_api.CommonResponse:
        if not request.get("path", "").startswith("/body-modify"):
            return response
            
        # Optionally add the header to response if we modified the request body
        if request.get("body_modified", False):
            self.add_header(response, BODY_MODIFIED_HEADER, "true")
        return response


if __name__ == "__main__":
    import logging

    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()]
    )

    serve(service=BodyModifyExtProcService())
