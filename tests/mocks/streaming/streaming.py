#!/usr/bin/env python
"""
Simple HTTP server that simulates a streaming LLM API response.
"""

import http.server
import json
import socketserver
import time
from http import HTTPStatus
import logging


logger = logging.getLogger(__name__)

PORT = 80


class StreamingHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests with a simple JSON response"""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        response = {"message": "Hello from streaming server", "path": self.path}
        data = json.dumps(response).encode()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        """Handle POST requests with either streaming or normal response"""
        # Read request body handling both Content-Length and Transfer-Encoding: chunked
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        is_chunked = "chunked" in transfer_encoding.lower()
        
        # Get content length from header or x-content-length (set by ExtProc)
        content_length = int(
            self.headers.get(
                "Content-Length", self.headers.get("x-content-length", "0")
            )
        )
        
        logger.debug(f"Content length: {content_length}, chunked: {is_chunked}")
        
        if is_chunked:
            body_bytes = bytearray()
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                try:
                    chunk_size = int(line, 16)
                    if chunk_size == 0:
                        # Last chunk
                        self.rfile.readline()  # Read trailing CRLF
                        break
                    body_bytes.extend(self.rfile.read(chunk_size))
                    self.rfile.readline()  # Read trailing CRLF
                except Exception as e:
                    logger.error(f"Error reading chunk: {e}")
                    break
            body = body_bytes.decode("utf-8") if body_bytes else "{}"
        elif content_length > 0:
            # Handle content with defined length
            body = self.rfile.read(content_length).decode("utf-8")
        else:
            body = "{}"
        
        logger.debug(f"Request body: {body}")

        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            request_data = {}

        path_is_completions = self.path.startswith("/completions")
        is_streaming = (
            path_is_completions  # Force streaming for all completions requests for this example
        )

        logger.debug(f"Received request: path={self.path}")
        logger.debug(f"RECEIVED BODY: {body}")
        logger.debug(f"PARSED DATA: {request_data}")
        logger.debug(f"Headers: {dict(self.headers)}")
        logger.debug(f"Using streaming response: {is_streaming}")

        if is_streaming:
            logger.debug("Sending streaming response")
            try:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                # Preserve important headers
                for header in self.headers:
                    if header.lower().startswith("x-"):
                        self.send_header(header, self.headers[header])
                # Add the proxy header to simulate what the LLM proxy would do
                self.send_header("x-llm-proxy", "true")
                self.end_headers()

                # Get model from the request body  
                model = request_data.get("model", "streaming-default-model")
                logger.debug(f"Using model from request body: {model}")
                
                # Send initial chunk
                initial_data = json.dumps(
                    {
                        "id": "chatcmpl-123",
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant"},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
                self.wfile.write(f"data: {initial_data}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.1)

                # Send a few content chunks
                for i in range(3):
                    chunk_data = json.dumps(
                        {
                            "id": "chatcmpl-123",
                            "object": "chat.completion.chunk",
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": f"part {i + 1} "},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )
                    chunk_text = f"data: {chunk_data}\n\n"
                    logger.debug(f"Sending chunk: {chunk_text.strip()}")
                    self.wfile.write(chunk_text.encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.1)

                # Send final chunk
                final_data = json.dumps(
                    {
                        "id": "chatcmpl-123",
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "completed"},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                )
                final_chunk = f"data: {final_data}\n\n"
                logger.debug(f"Sending final chunk: {final_chunk.strip()}")
                self.wfile.write(final_chunk.encode("utf-8"))

                # Send completion marker
                done_marker = "data: [DONE]\n\n"
                logger.debug(f"Sending completion marker: {done_marker.strip()}")
                self.wfile.write(done_marker.encode("utf-8"))
                self.wfile.flush()
                logger.debug("Streaming response complete")

            except Exception as e:
                logger.debug(f"Error during streaming: {e}")
        else:
            # Send a normal JSON response
            logger.debug("Sending normal JSON response")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")

            response = {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
                "message": "This is a non-streaming response",
            }

            # Add the requested model if it was in the request
            if "model" in request_data:
                response["model"] = request_data["model"]

            data = json.dumps(response).encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            logger.debug("Normal response complete")


def run_server():
    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(
        level=logging.DEBUG, format=FORMAT, handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)

    with socketserver.TCPServer(("", PORT), StreamingHandler) as httpd:
        logger.info(f"StreamingServer listening on port {PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
