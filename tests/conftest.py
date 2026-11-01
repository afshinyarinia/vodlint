from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest


@pytest.fixture
def ts_bytes():
    return (bytes([0x47]) + bytes(187)) * 2


@pytest.fixture
def media_text():
    return (
        "#EXTM3U\n#EXT-X-TARGETDURATION:10\n"
        "#EXTINF:9.9,\na.ts\n#EXTINF:1.1,\nb.ts\n#EXT-X-ENDLIST\n"
    )


@pytest.fixture
def http_server():
    """Real HTTP transport with per-test routes and observable requests."""
    routes = {}
    seen = []
    counts = Counter()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            counts[self.path] += 1
            seen.append((self.path, dict(self.headers)))
            response = routes.get(self.path, (404, {}, b"missing"))
            if callable(response):
                response = response(self, counts[self.path])
            if isinstance(response, str):
                response = response.encode()
            if isinstance(response, bytes):
                response = (200, {}, response)
            status, headers, body = response
            try:
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, str(value))
                if "Content-Length" not in headers:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Expected when a client enforces a timeout or byte limit.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(
            url=f"http://127.0.0.1:{server.server_port}",
            routes=routes,
            seen=seen,
            counts=counts,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
