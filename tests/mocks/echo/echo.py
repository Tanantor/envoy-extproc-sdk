import http.server
import json
import logging
from os import environ
import socketserver
from urllib.parse import parse_qs

ECHO_PORT = int(environ.get("ECHO_PORT", "80"))

Handler = http.server.BaseHTTPRequestHandler

ECHO_MESSAGE = environ.get("ECHO_MESSAGE", "Hello")

logger = logging.getLogger(__name__)


class H(Handler):
    protocol_version = "HTTP/1.0"
    rsp = {"method": None, "path": None, "headers": {}, "body": "", "message": ECHO_MESSAGE}

    def write_response(self):
        # Reset response for each new request to avoid state bleeding between requests
        self.rsp = {"method": None, "path": None, "headers": {}, "body": "", "message": ECHO_MESSAGE}
        self.rsp["method"] = self.command.lower()
        if self.path.startswith("/redirect"):
            self.send_response(308)
            _, _, queries = self.path.partition("?")
            params = parse_qs(queries)
            self.send_header("location", params["location"][0])
        else:
            self.send_response(200)

        self.rsp["path"] = self.path
        self.rsp["headers"] = {k: v for k, v in self.headers.items()}
        # Check if we're getting chunked encoding
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        is_chunked = "chunked" in transfer_encoding.lower()
        
        content_length = int(
            self.headers.get(
                "Content-Length", self.headers.get("x-content-length", "0")
            )
        )
        logger.debug(f"content_length: {content_length}, chunked: {is_chunked}")
        
        if is_chunked:
            # Handle chunked encoding
            data = b""
            while True:
                # Read the chunk size line
                chunk_size_line = self.rfile.readline().strip()
                logger.debug(f"chunk_size_line: {chunk_size_line}")
                
                # If empty, we're done
                if not chunk_size_line:
                    break
                    
                # Parse the chunk size (hex number)
                try:
                    chunk_size = int(chunk_size_line, 16)
                except ValueError:
                    logger.error(f"Invalid chunk size: {chunk_size_line}")
                    break
                    
                # If chunk size is 0, we're done
                if chunk_size == 0:
                    # Read the final CRLF
                    self.rfile.readline()
                    break
                    
                # Read the chunk data
                chunk_data = self.rfile.read(chunk_size)
                data += chunk_data
                
                # Read the CRLF at the end of the chunk
                self.rfile.readline()
            
            self.rsp["body"] = data.decode('utf-8')
            logger.debug(f"Assembled chunked body: {self.rsp['body']}")
            
        elif content_length > 0:
            # Standard content-length approach
            self.rsp["body"] = self.rfile.read(content_length).decode()
            logger.debug(f"content_length: {content_length}")
            logger.debug(f"body: {self.rsp['body']}")
        b = json.dumps(self.rsp).encode("UTF-8")
        logger.debug(f"write_response: {self.rsp}")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def do_GET(self):
        self.write_response()

    def do_POST(self):
        self.write_response()

    def do_PUT(self):
        self.write_response()

    def do_PATH(self):
        self.write_response()

    def do_DELETE(self):
        self.write_response()

    def do_OPTION(self):
        self.write_response()


if __name__ == "__main__":
    FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=FORMAT, handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger(__name__)

    with socketserver.TCPServer(("", ECHO_PORT), H) as httpd:
        logger.info(f"EchoServer listening on port {ECHO_PORT}")
        httpd.serve_forever()
