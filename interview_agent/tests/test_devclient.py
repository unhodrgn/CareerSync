"""The developer page's server (M5 S4): what it serves, what it forwards, and what it must never forward. A fake backend runs in a thread."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from interview_agent.devclient import serve

DEVCLIENT = Path(serve.__file__).parent


class FakeBackend(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        FakeBackend.seen.append({"method": self.command, "path": self.path, "body": body, "authorization": self.headers.get("Authorization"), "cookie": self.headers.get("Cookie")})
        payload = json.dumps({"echo": self.path}).encode()
        self.send_response(409 if self.path.split("?")[0].endswith("/conflict") else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "max-age=600")  # a backend header that must not survive
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = do_PUT = do_PATCH = _answer

    def log_message(self, *args):
        pass


def serve_in_thread(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


@pytest.fixture
def stack():
    FakeBackend.seen = []
    backend = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackend)
    serve_in_thread(backend)
    page = serve.make_server(0, backend=f"http://127.0.0.1:{backend.server_address[1]}")
    serve_in_thread(page)
    client = httpx.Client(base_url=f"http://127.0.0.1:{page.server_address[1]}", timeout=10)
    yield client, page
    client.close()
    page.shutdown()
    backend.shutdown()
    page.server_close()
    backend.server_close()


def test_it_listens_on_the_loopback_address_only(stack):
    _client, page = stack
    assert page.server_address[0] == "127.0.0.1" == serve.HOST


def test_it_serves_the_page_and_its_script_with_no_store(stack):
    client, _ = stack
    for path, marker in (("/", "livekit-client@2.24.1"), ("/app.js", "READY_ATTRIBUTE"), ("/style.css", "body")):
        response = client.get(path)
        assert response.status_code == 200 and marker in response.text and response.headers["cache-control"] == "no-store", path


def test_the_page_pins_livekit_client_with_an_integrity_hash_and_publishes_the_microphone_only():
    html = (DEVCLIENT / "index.html").read_text(encoding="utf-8")
    tag = re.search(r"<script src=\"https://cdn\.jsdelivr\.net/npm/livekit-client@(\d+\.\d+\.\d+)/[^\"]+\"\s+integrity=\"sha384-[A-Za-z0-9+/=]+\"\s+crossorigin=\"anonymous\"", html)
    assert tag and tag.group(1) == "2.24.1"  # an exact version with a Subresource Integrity hash, as the PoC page has
    assert 'id="avatar-video"' in html and 'id="preview-video"' in html and "muted" in html
    script = (DEVCLIENT / "app.js").read_text(encoding="utf-8")
    assert "setMicrophoneEnabled(true)" in script and "setCameraEnabled" not in script and "setScreenShareEnabled" not in script
    assert "setTrackSubscriptionPermissions" in script and "lk.publish_on_behalf" in script
    assert "innerHTML" not in script and "eval(" not in script  # everything shown goes in as text


def test_an_api_call_is_forwarded_with_its_method_body_and_token_and_nothing_else(stack):
    client, _ = stack
    response = client.post("/api/auth/login", json={"email": "a@b.test"}, headers={"Authorization": "Bearer t", "Cookie": "x=1", "X-Other": "no"})
    assert response.status_code == 200 and response.json() == {"echo": "/api/auth/login"}
    (seen,) = FakeBackend.seen
    assert seen["method"] == "POST" and json.loads(seen["body"]) == {"email": "a@b.test"} and seen["authorization"] == "Bearer t" and seen["cookie"] is None
    assert client.delete("/api/interview-sessions/5").status_code == 200 and FakeBackend.seen[-1]["method"] == "DELETE"


def test_the_backends_status_and_query_pass_through_and_its_cache_header_is_replaced(stack):
    client, _ = stack
    response = client.get("/api/interview-sessions/5/conflict?limit=3")
    assert response.status_code == 409 and response.headers["cache-control"] == "no-store"
    assert FakeBackend.seen[-1]["path"] == "/api/interview-sessions/5/conflict?limit=3"


@pytest.mark.parametrize(
    "path",
    ["/api/internal/interview-sessions/1/context", "/api/internal", "/api/internal/", "/api/%69nternal/interview-sessions/1/events", "/api/jobs/../internal/x",
     "/api/../etc/passwd", "/api/%2e%2e/x", "/api/internal%2Fx", "/apix/jobs", "/api"],
)
def test_the_internal_api_and_anything_that_could_reach_it_or_leave_api_is_never_forwarded(stack, path):
    client, _ = stack
    for method in ("GET", "POST"):
        response = client.request(method, path)
        assert response.status_code in (404, 405), (method, path, response.status_code)
    assert FakeBackend.seen == [], path


def test_a_large_body_a_bad_length_and_head_on_the_api_are_refused(stack):
    client, _ = stack
    try:
        status = client.post("/api/x", content=b"x" * (serve.MAX_BODY_BYTES + 1)).status_code
    except httpx.TransportError:  # the server refuses at once and closes the connection: the client may still be sending (a reset on Windows)
        status = 413
    assert status == 413
    assert client.head("/api/jobs").status_code == 405
    assert FakeBackend.seen == []


def test_an_unreachable_backend_is_a_502():
    page = serve.make_server(0, backend="http://127.0.0.1:1")
    serve_in_thread(page)
    try:
        response = httpx.get(f"http://127.0.0.1:{page.server_address[1]}/api/jobs", timeout=10)
        assert response.status_code == 502
    finally:
        page.shutdown()
        page.server_close()


def test_there_is_no_directory_listing_and_no_way_out_of_the_folder(stack):
    client, _ = stack
    assert client.get("/__pycache__/").status_code == 404
    for path in ("/../README.md", "/..%2fREADME.md", "/%2e%2e/requirements.txt"):
        assert client.get(path).status_code in (400, 403, 404), path
