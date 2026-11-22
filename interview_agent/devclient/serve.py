"""The developer page for the voice interview and a forwarder to the backend (M5 S4; docs/DECISIONS.md D80).

    python -m interview_agent.devclient.serve [--port 8788]      then open http://127.0.0.1:8788/

It serves the files of this folder and forwards `/api/...` to the backend (`INTERVIEW_AGENT_BACKEND_URL`, default http://127.0.0.1:8000), so the
page runs on one origin and the backend needs no CORS setting. What it will not do:

- listen on anything but 127.0.0.1;
- forward the agent's internal API (`/api/internal/...`): that is for the agent, with its secret, and a browser page must not reach it;
- forward anything outside `/api/`, a path with `..`, or a body over 1 MB;
- log a request body, a token or a header (the request line only).

Every response, the forwarded ones too, says `Cache-Control: no-store`. Standard library only."""
from __future__ import annotations

import argparse
import http.client
import logging
import os
import posixpath
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

log = logging.getLogger("interview_agent.devclient")

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
MAX_BODY_BYTES = 1_000_000
FORWARDED_REQUEST_HEADERS = ("authorization", "content-type", "accept")
DROPPED_RESPONSE_HEADERS = {"transfer-encoding", "connection", "content-length", "keep-alive", "cache-control", "server", "date"}


def forwardable(raw_path: str) -> bool:
    """True for `/api/...` outside the internal API, without a way out of it."""
    path = unquote(urlsplit(raw_path).path)
    if ".." in path.split("/") or "\\" in path or "\x00" in path:
        return False
    normal = posixpath.normpath(path)
    return normal.startswith("/api/") and normal != "/api/internal" and not normal.startswith("/api/internal/")


class Handler(SimpleHTTPRequestHandler):
    backend = "http://127.0.0.1:8000"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002  (the request line only: no body, no header, no token)
        log.info("%s", format % args)

    def list_directory(self, path):  # no directory listing
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def do_GET(self) -> None:
        if self.path.startswith("/api"):
            return self._forward()
        super().do_GET()

    def do_HEAD(self) -> None:
        if self.path.startswith("/api"):
            return self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
        super().do_HEAD()

    def do_POST(self) -> None:
        self._forward()

    do_PUT = do_PATCH = do_DELETE = do_POST

    def _forward(self) -> None:
        if not forwardable(self.path):
            return self.send_error(HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_error(HTTPStatus.BAD_REQUEST)
        if length < 0 or length > MAX_BODY_BYTES:
            return self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        body = self.rfile.read(length) if length else None
        target = urlsplit(self.backend)
        connection = (http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection)(target.hostname, target.port, timeout=30)
        headers = {name: self.headers[name] for name in FORWARDED_REQUEST_HEADERS if self.headers.get(name)}
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            answer = connection.getresponse()
            payload = answer.read()
        except OSError:
            return self.send_error(HTTPStatus.BAD_GATEWAY, "the backend does not answer")
        finally:
            connection.close()
        self.send_response(answer.status)
        for name, value in answer.getheaders():
            if name.lower() not in DROPPED_RESPONSE_HEADERS:
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_server(port: int = 8788, backend: str | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"backend": (backend or os.environ.get("INTERVIEW_AGENT_BACKEND_URL") or Handler.backend).rstrip("/")})
    return ThreadingHTTPServer((HOST, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = make_server(args.port)
    print(f"http://{HOST}:{args.port}/  ->  {server.RequestHandlerClass.backend}   (Ctrl+C stops)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
